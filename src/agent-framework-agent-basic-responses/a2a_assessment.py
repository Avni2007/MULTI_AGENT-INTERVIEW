"""A2A transport for the Mock Test Agent.

The assessment model remains owned by webapp.py. This module owns the
protocol boundary: agent card, JSON-RPC task handling, and response extraction.
"""

from __future__ import annotations

import json
import uuid
from collections.abc import Awaitable, Callable
from typing import Any

# Ensure protobuf FieldDescriptor compatibility on all platforms
try:
    import a2a.server.routes._proto_schema as _ps
    from google.protobuf.descriptor import FieldDescriptor

    _orig_field_schema = _ps.field_schema

    def _safe_field_schema(field: Any, components: dict[str, Any]) -> dict[str, Any]:
        is_rep = getattr(field, "is_repeated", getattr(field, "label", None) == getattr(field, "LABEL_REPEATED", 3))
        if field.message_type and field.message_type.GetOptions().map_entry:
            val_field = field.message_type.fields_by_name["value"]
            return {
                "type": "object",
                "additionalProperties": _safe_field_schema(val_field, components),
            }
        if field.type == FieldDescriptor.TYPE_MESSAGE:
            item = _ps.message_schema(field.message_type, components)
            if not is_rep and not _ps._is_required(field) and "$ref" in item:
                return {"oneOf": [item, {"type": "null"}], "example": None}
        elif field.type == FieldDescriptor.TYPE_ENUM:
            values = [v.name for v in field.enum_type.values]
            ex = next((v for v in values if "UNSPECIFIED" not in v and "UNKNOWN" not in v), values[0] if values else None)
            item = {"type": "string", "enum": values}
            if ex:
                item["example"] = ex
        else:
            item = dict(_ps._PROTO_SCALAR_SCHEMAS.get(field.type, {"type": "string"}))
            if field.type == FieldDescriptor.TYPE_STRING:
                item["example"] = field.name if _ps._is_required(field) else ""
            elif field.type == FieldDescriptor.TYPE_BOOL:
                item["example"] = False

        if is_rep:
            array_schema: dict[str, Any] = {"type": "array", "items": item}
            item_example = components.get(item["$ref"].split("/")[-1], {}).get("example") if "$ref" in item else item.get("example")
            if item_example is not None:
                array_schema["example"] = [item_example]
            return array_schema
        return item

    _ps.field_schema = _safe_field_schema
except Exception:
    pass

from a2a.server.agent_execution import AgentExecutor, RequestContext
from a2a.server.events import EventQueue
from a2a.server.request_handlers import DefaultRequestHandler
from a2a.server.routes.agent_card_routes import create_agent_card_routes
from a2a.server.routes.fastapi_routes import add_a2a_routes_to_fastapi
from a2a.server.routes.jsonrpc_routes import create_jsonrpc_routes
from a2a.server.tasks.inmemory_task_store import InMemoryTaskStore
from a2a.types import a2a_pb2

ASSESSMENT_A2A_PATH = "/a2a"


class AssessmentA2AExecutor(AgentExecutor):
    def __init__(self, generate_questions: Callable[[dict[str, Any]], Awaitable[Any]]) -> None:
        self._generate_questions = generate_questions

    async def execute(self, context: RequestContext, event_queue: EventQueue) -> None:
        raw_payload = "".join(part.text for part in context.message.parts if part.text)
        payload = json.loads(raw_payload)

        category = payload.get("category", "coding")
        selected_language = payload.get("selected_language")
        difficulty = payload.get("difficulty", "medium")
        question_count = payload.get("question_count", 5)

        question_set = await self._generate_questions({
            "category": category,
            "supported_language": selected_language,
            "difficulty": difficulty,
            "question_count": question_count,
            "detected_skills": payload.get("technical_skills", []) + payload.get("frameworks", []) + payload.get("libraries", []),
            "projects": payload.get("projects", []),
        })
        response = {
            "category": getattr(question_set, "category", category),
            "language": getattr(question_set, "language", selected_language),
            "difficulty": getattr(question_set, "difficulty", difficulty),
            "questions": [q.model_dump() for q in question_set.questions],
        }
        await event_queue.enqueue_event(a2a_pb2.Message(
            message_id=uuid.uuid4().hex,
            role=a2a_pb2.ROLE_AGENT,
            parts=[a2a_pb2.Part(text=json.dumps(response, ensure_ascii=False))],
        ))

    async def cancel(self, context: RequestContext, event_queue: EventQueue) -> None:
        await event_queue.enqueue_event(a2a_pb2.Message(
            message_id=uuid.uuid4().hex,
            role=a2a_pb2.ROLE_AGENT,
            parts=[a2a_pb2.Part(text=json.dumps({"error": "Assessment task cancelled"}))],
        ))


def install_assessment_a2a(app: Any, generate_questions: Callable[[dict[str, Any]], Awaitable[Any]]) -> None:
    card = a2a_pb2.AgentCard(
        name="InterviewIQ Mock Test Agent",
        description="Generates personalized coding, DSA, Core CS, aptitude, and resume-based assessments.",
        version="2.0.0",
        supported_interfaces=[a2a_pb2.AgentInterface(
            url=ASSESSMENT_A2A_PATH,
            protocol_binding="JSONRPC",
            protocol_version="1.0",
        )],
        capabilities=a2a_pb2.AgentCapabilities(streaming=False, push_notifications=False),
        default_input_modes=["text"],
        default_output_modes=["text"],
        skills=[a2a_pb2.AgentSkill(
            id="interviewiq-assessment",
            name="InterviewIQ Assessment Generator",
            description="Generates category and language-tailored mock tests grounded in candidate resume data.",
            tags=["interview", "coding", "dsa", "assessment", "resume-intelligence"],
            input_modes=["text"],
            output_modes=["text"],
        )],
    )
    handler = DefaultRequestHandler(
        agent_executor=AssessmentA2AExecutor(generate_questions),
        task_store=InMemoryTaskStore(),
        agent_card=card,
    )
    add_a2a_routes_to_fastapi(
        app,
        agent_card_routes=create_agent_card_routes(card),
        jsonrpc_routes=create_jsonrpc_routes(handler, rpc_url=ASSESSMENT_A2A_PATH),
    )
