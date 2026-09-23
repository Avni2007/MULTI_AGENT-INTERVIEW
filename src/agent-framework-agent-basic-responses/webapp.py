"""InterviewIQ — FastAPI Web Application & Agent Orchestration Service.

Integrates Microsoft Azure Foundry, Azure Document Intelligence,
Agent Framework, A2A protocol, and SQLite authentication.
"""

from __future__ import annotations

import asyncio
import io
import json
import logging
import os
import textwrap
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import Any

from dotenv import load_dotenv
from fastapi import Cookie, Depends, FastAPI, File, Form, Header, HTTPException, Response, UploadFile
from fastapi.responses import HTMLResponse, JSONResponse
from pydantic import BaseModel, Field

# ── Azure Document Intelligence ──────────────────────────────────────────────
from azure.ai.formrecognizer import DocumentAnalysisClient
from azure.core.credentials import AzureKeyCredential
from azure.core.exceptions import HttpResponseError

# ── Azure Identity ───────────────────────────────────────────────────────────
from azure.identity import DefaultAzureCredential

# ── Agent Framework & Foundry ────────────────────────────────────────────────
from agent_framework.a2a import A2AAgent
from agent_framework.foundry import FoundryChatClient

# ── Project Modules ──────────────────────────────────────────────────────────
import auth
from a2a_assessment import install_assessment_a2a
import agents
from assessment import (
    AssessmentQuestionSet,
    ExecutionRequest,
    RunCodeRequest,
    RunCodeResult,
    canonical_language,
    check_runtime_support,
    execute_question,
    extract_resume_skills,
    new_assessment_id,
    public_question,
    run_code_sandbox,
)

# ─────────────────────────────────────────────────────────────────────────────
# Logging
# ─────────────────────────────────────────────────────────────────────────────
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s — %(message)s",
)
logger = logging.getLogger("interviewiq")

# ─────────────────────────────────────────────────────────────────────────────
# Environment Validation
# ─────────────────────────────────────────────────────────────────────────────
load_dotenv()

_REQUIRED_VARS = [
    "FOUNDRY_PROJECT_ENDPOINT",
    "AZURE_DOCUMENT_INTELLIGENCE_ENDPOINT",
    "AZURE_DOCUMENT_INTELLIGENCE_KEY",
]
_missing = [v for v in _REQUIRED_VARS if not os.environ.get(v)]
if _missing:
    raise RuntimeError(
        f"Missing required environment variables: {', '.join(_missing)}. "
        "Check your .env file."
    )

MODEL_NAME = os.getenv("AZURE_AI_MODEL_DEPLOYMENT_NAME") or os.getenv("FOUNDRY_MODEL_NAME")
if not MODEL_NAME:
    raise RuntimeError(
        "Model deployment name is not configured. "
        "Set AZURE_AI_MODEL_DEPLOYMENT_NAME or FOUNDRY_MODEL_NAME in .env."
    )

# ─────────────────────────────────────────────────────────────────────────────
# Azure Clients & Orchestrator Initialisation
# ─────────────────────────────────────────────────────────────────────────────
document_client = DocumentAnalysisClient(
    endpoint=os.environ["AZURE_DOCUMENT_INTELLIGENCE_ENDPOINT"],
    credential=AzureKeyCredential(os.environ["AZURE_DOCUMENT_INTELLIGENCE_KEY"]),
)

foundry_client = FoundryChatClient(
    project_endpoint=os.environ["FOUNDRY_PROJECT_ENDPOINT"],
    model=MODEL_NAME,
    credential=DefaultAzureCredential(),
)

orchestrator = agents.InterviewIQOrchestrator(foundry_client)

_doc_executor = ThreadPoolExecutor(max_workers=4)

# ─────────────────────────────────────────────────────────────────────────────
# Constants & Memory Store
# ─────────────────────────────────────────────────────────────────────────────
MAX_FILE_SIZE_BYTES = 10 * 1024 * 1024  # 10 MB
ALLOWED_EXTENSIONS = {".pdf", ".docx", ".doc"}
HERE = Path(__file__).parent

# Active in-memory test sessions and cached candidate analysis
assessment_sessions: dict[str, dict[str, Any]] = {}
current_resume_session: dict[str, Any] | None = None

# Initialize SQLite tables
auth.init_db()

# ─────────────────────────────────────────────────────────────────────────────
# FastAPI App
# ─────────────────────────────────────────────────────────────────────────────
app = FastAPI(title="InterviewIQ", version="2.0.0")


# ── Dependency: Auth Helper ──────────────────────────────────────────────────
def get_user_from_request(
    authorization: str | None = Header(default=None),
    session_token: str | None = Cookie(default=None),
) -> dict[str, Any] | None:
    token = None
    if authorization and authorization.startswith("Bearer "):
        token = authorization[7:].strip()
    elif session_token:
        token = session_token
    if not token:
        return None
    return auth.get_user_by_session(token)


# ── Request Models ───────────────────────────────────────────────────────────
class SignupRequest(BaseModel):
    name: str = Field(min_length=2)
    email: str = Field(min_length=5)
    password: str = Field(min_length=6)


class LoginRequest(BaseModel):
    email: str = Field(min_length=5)
    password: str = Field(min_length=6)


class TestPlanRequest(BaseModel):
    category: str = "coding"
    selected_language: str | None = None
    difficulty: str = "medium"
    question_count: int = 5
    duration_minutes: int = 45


class AssessmentStartRequest(BaseModel):
    category: str = "coding"
    selected_language: str | None = None
    difficulty: str = "medium"
    question_count: int = 5
    duration_minutes: int = 45


# ── Helper: Document Intelligence Extraction ─────────────────────────────────
def _extract_docx_fallback(file_bytes: bytes) -> str:
    """Fallback extraction for DOCX using python-docx."""
    try:
        from docx import Document as DocxDocument  # type: ignore

        doc = DocxDocument(io.BytesIO(file_bytes))
        lines = [para.text.strip() for para in doc.paragraphs if para.text.strip()]
        for table in doc.tables:
            for row in table.rows:
                for cell in row.cells:
                    t = cell.text.strip()
                    if t and t not in lines:
                        lines.append(t)
        return "\n".join(lines).strip()
    except Exception as exc:
        logger.warning("DOCX fallback extraction failed: %s", exc)
        return ""


def _extract_text_blocking(file_bytes: bytes, filename: str) -> str:
    """Run Azure Document Intelligence synchronously inside thread pool."""
    suffix = Path(filename).suffix.lower()
    logger.info("Sending %d bytes (%s) to Azure Document Intelligence...", len(file_bytes), suffix)
    try:
        poller = document_client.begin_analyze_document(
            model_id="prebuilt-read",
            document=io.BytesIO(file_bytes),
        )
        result = poller.result()
    except HttpResponseError as exc:
        logger.error("Document Intelligence HTTP error: %s", exc)
        raise RuntimeError(f"Azure Document Intelligence error: {exc.message or str(exc)}")

    lines = []
    for page in result.pages:
        for line in page.lines:
            lines.append(line.content)
    text = "\n".join(lines).strip()
    logger.info("Azure Document Intelligence extracted %d characters.", len(text))

    if not text and suffix in (".docx", ".doc"):
        logger.info("Document Intelligence returned 0 chars for DOCX — trying fallback.")
        text = _extract_docx_fallback(file_bytes)

    return text


async def _extract_text(file_bytes: bytes, filename: str) -> str:
    loop = asyncio.get_event_loop()
    try:
        return await loop.run_in_executor(_doc_executor, _extract_text_blocking, file_bytes, filename)
    except RuntimeError as exc:
        raise HTTPException(status_code=502, detail=str(exc))


# ── Helper: A2A Question Generation Protocol ─────────────────────────────────
async def _generate_assessment_questions(context: dict[str, Any]) -> AssessmentQuestionSet:
    category = context.get("category", "coding")
    language = context.get("supported_language")
    difficulty = context.get("difficulty", "medium")
    question_count = context.get("question_count", 5)

    plan = {
        "category": category,
        "language": language,
        "difficulty": difficulty,
        "question_count": question_count,
        "duration_minutes": 45,
    }
    candidate_context = {
        "supported_languages": [language] if language else [],
        "detected_skills": context.get("detected_skills", []),
        "projects": context.get("projects", []),
    }
    return await orchestrator.forge_questions(plan, candidate_context)


install_assessment_a2a(app, _generate_assessment_questions)


def _assessment_a2a_payload(
    context: dict[str, Any],
    category: str,
    selected_language: str | None,
    difficulty: str,
    question_count: int,
) -> dict[str, Any]:
    skills = context.get("detected_skills", [])
    languages = context.get("supported_languages", [])
    frameworks = context.get("frameworks", [])
    libraries = context.get("libraries", [])
    technical_skills = [s for s in skills if s not in set(languages) | set(frameworks) | set(libraries)]
    return {
        "resume_text": context.get("resume_text", ""),
        "category": category,
        "programming_languages": languages,
        "technical_skills": technical_skills,
        "frameworks": frameworks,
        "libraries": libraries,
        "projects": context.get("projects", []),
        "selected_language": selected_language,
        "difficulty": difficulty,
        "question_count": question_count,
    }


async def _send_assessment_a2a(payload: dict[str, Any]) -> AssessmentQuestionSet:
    base_url = os.getenv("ASSESSMENT_A2A_URL", "http://127.0.0.1:8000")
    rpc_url = f"{base_url.rstrip('/')}/a2a"
    try:
        async with A2AAgent(
            url=rpc_url,
            supported_protocol_bindings=["JSONRPC"],
            timeout=180.0,
        ) as mock_test_agent:
            response = await mock_test_agent.run(json.dumps(payload, ensure_ascii=False))
            raw_questions = response.text
    except Exception as exc:
        logger.warning("A2A handoff fallback to direct Question Forge: %s", exc)
        # Direct fallback to Question Forge Agent
        plan = {
            "category": payload.get("category", "coding"),
            "language": payload.get("selected_language"),
            "difficulty": payload.get("difficulty", "medium"),
            "question_count": payload.get("question_count", 5),
        }
        return await orchestrator.forge_questions(plan, payload)

    if not raw_questions:
        raise HTTPException(status_code=502, detail="Mock Test Agent A2A response contained no question JSON.")

    try:
        data = json.loads(raw_questions)
        return AssessmentQuestionSet.model_validate(data)
    except Exception as exc:
        logger.error("A2A question validation error: %s", exc)
        # Direct fallback
        plan = {
            "category": payload.get("category", "coding"),
            "language": payload.get("selected_language"),
            "difficulty": payload.get("difficulty", "medium"),
            "question_count": payload.get("question_count", 5),
        }
        return await orchestrator.forge_questions(plan, payload)


# ─────────────────────────────────────────────────────────────────────────────
# HTML Routes
# ─────────────────────────────────────────────────────────────────────────────
@app.get("/", response_class=HTMLResponse)
@app.get("/resume-analysis", response_class=HTMLResponse)
@app.get("/mock-tests", response_class=HTMLResponse)
@app.get("/results", response_class=HTMLResponse)
@app.get("/dashboard", response_class=HTMLResponse)
@app.get("/login", response_class=HTMLResponse)
async def serve_ui():
    html_path = HERE / "index.html"
    if not html_path.exists():
        raise HTTPException(status_code=404, detail="index.html not found.")
    return HTMLResponse(content=html_path.read_text(encoding="utf-8"))


# ─────────────────────────────────────────────────────────────────────────────
# Auth Endpoints
# ─────────────────────────────────────────────────────────────────────────────
@app.post("/auth/signup")
async def signup(req: SignupRequest, response: Response):
    try:
        user = auth.register_user(req.name, req.email, req.password)
        token = auth.create_session(user["id"])
        response.set_cookie(key="session_token", value=token, httponly=True, max_age=86400 * 7, samesite="lax")
        return {"success": True, "user": user, "token": token}
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))


@app.post("/auth/login")
async def login(req: LoginRequest, response: Response):
    user = auth.authenticate_user(req.email, req.password)
    if not user:
        raise HTTPException(status_code=401, detail="Invalid email or password.")
    token = auth.create_session(user["id"])
    response.set_cookie(key="session_token", value=token, httponly=True, max_age=86400 * 7, samesite="lax")
    return {"success": True, "user": user, "token": token}


@app.get("/auth/me")
async def current_user(user: dict[str, Any] | None = Depends(get_user_from_request)):
    if not user:
        return {"authenticated": False, "user": None, "history": []}
    history = auth.get_user_test_history(user["id"])
    return {"authenticated": True, "user": user, "history": history}


@app.post("/auth/logout")
async def logout(
    response: Response,
    session_token: str | None = Cookie(default=None),
    authorization: str | None = Header(default=None),
):
    token = None
    if authorization and authorization.startswith("Bearer "):
        token = authorization[7:].strip()
    elif session_token:
        token = session_token
    if token:
        auth.delete_session(token)
    response.delete_cookie(key="session_token")
    return {"success": True}


# ─────────────────────────────────────────────────────────────────────────────
# Core Application Endpoints
# ─────────────────────────────────────────────────────────────────────────────
@app.post("/analyze")
async def analyze_resume(
    file: UploadFile = File(...),
    job_description: str = Form(default=""),
    user: dict[str, Any] | None = Depends(get_user_from_request),
):
    """Resume Intelligence Agent: extracts text and analyzes resume evidence."""
    filename = file.filename or "resume.pdf"
    suffix = Path(filename).suffix.lower()
    if suffix not in ALLOWED_EXTENSIONS:
        raise HTTPException(
            status_code=400,
            detail=f"Unsupported file type '{suffix}'. Please upload a PDF or DOCX file.",
        )

    file_bytes = await file.read()
    if len(file_bytes) == 0:
        raise HTTPException(status_code=400, detail="Uploaded file is empty.")
    if len(file_bytes) > MAX_FILE_SIZE_BYTES:
        raise HTTPException(
            status_code=413,
            detail=f"File too large ({len(file_bytes) // 1024} KB). Maximum allowed size is 10 MB.",
        )

    # Extract text using Azure Document Intelligence
    resume_text = await _extract_text(file_bytes, filename)
    if not resume_text:
        raise HTTPException(
            status_code=422,
            detail="Could not extract selectable text from the uploaded document.",
        )

    # Run Resume Intelligence Agent
    analysis = await orchestrator.run_resume_analysis(resume_text, job_description or None)

    # Extract strictly verified skills and programming languages
    context = extract_resume_skills(resume_text, analysis)
    context["resume_text"] = resume_text

    # Runtime capability mapping for all extracted languages
    runtime_capabilities = {
        lang: check_runtime_support(lang) for lang in context["supported_languages"]
    }
    context["runtime_capabilities"] = runtime_capabilities

    analysis["assessment_context"] = context

    global current_resume_session
    current_resume_session = {
        "context": context,
        "analysis": analysis,
        "user_id": user["id"] if user else None,
    }

    return JSONResponse(content=analysis)


@app.get("/session/current")
async def get_current_session(user: dict[str, Any] | None = Depends(get_user_from_request)):
    """Retrieve current resume analysis state and available configuration options."""
    if not current_resume_session:
        return {"analyzed": False, "user": user}

    ctx = current_resume_session["context"]
    supported_langs = ctx.get("supported_languages", [])
    runtime_capabilities = {lang: check_runtime_support(lang) for lang in supported_langs}

    return {
        "analyzed": True,
        "user": user,
        "supported_language": ctx.get("supported_language"),
        "supported_languages": supported_langs,
        "frameworks": ctx.get("frameworks", []),
        "libraries": ctx.get("libraries", []),
        "tools": ctx.get("tools", []),
        "detected_skills": ctx.get("detected_skills", []),
        "projects": ctx.get("projects", []),
        "runtime_capabilities": runtime_capabilities,
        "assessment_id": current_resume_session.get("assessment_id"),
    }


@app.post("/assessment/plan")
async def plan_assessment(req: TestPlanRequest):
    """Adaptive Test Planner: creates a verified plan from resume skills and test settings."""
    if not current_resume_session:
        raise HTTPException(status_code=409, detail="Analyze your resume first to unlock personalized mock tests.")

    context = current_resume_session["context"]
    supported_languages = context.get("supported_languages", [])

    # Validate language for coding / dsa tests
    if req.category in {"coding", "dsa"}:
        if not req.selected_language or req.selected_language not in supported_languages:
            raise HTTPException(
                status_code=400,
                detail=f"Please choose a programming language extracted from your resume ({', '.join(supported_languages) if supported_languages else 'None detected'}).",
            )

    plan = await orchestrator.plan_assessment(
        context,
        category=req.category,
        language=req.selected_language,
        difficulty=req.difficulty,
        question_count=req.question_count,
        duration_minutes=req.duration_minutes,
    )
    return plan


@app.post("/assessment/start")
async def start_assessment(req: AssessmentStartRequest):
    """Question Forge Agent (with A2A protocol): generates and returns structured questions."""
    if not current_resume_session:
        raise HTTPException(status_code=409, detail="Analyze your resume first to unlock personalized mock tests.")

    context = current_resume_session["context"]
    supported_languages = context.get("supported_languages", [])

    # For coding and DSA, require an extracted language
    if req.category in {"coding", "dsa"}:
        if not req.selected_language or req.selected_language not in supported_languages:
            raise HTTPException(
                status_code=400,
                detail=f"Selected language must be one of your resume's detected languages: {', '.join(supported_languages) if supported_languages else 'None detected'}.",
            )

    a2a_payload = _assessment_a2a_payload(
        context,
        category=req.category,
        selected_language=req.selected_language,
        difficulty=req.difficulty,
        question_count=req.question_count,
    )

    question_set = await _send_assessment_a2a(a2a_payload)

    assessment_id = new_assessment_id()
    assessment_sessions[assessment_id] = {
        "id": assessment_id,
        "category": req.category,
        "language": req.selected_language,
        "difficulty": req.difficulty,
        "duration_minutes": req.duration_minutes,
        "questions": {q.id: q for q in question_set.questions},
        "results": {},
        "skills": context.get("detected_skills", []),
    }
    current_resume_session["assessment_id"] = assessment_id

    # Return public view (hidden tests stripped)
    return {
        "assessment_id": assessment_id,
        "category": req.category,
        "language": req.selected_language,
        "difficulty": req.difficulty,
        "duration_minutes": req.duration_minutes,
        "skills": context.get("detected_skills", []),
        "questions": [public_question(q) for q in question_set.questions],
    }


@app.post("/assessment/run")
async def run_assessment_code(req: RunCodeRequest):
    """Code Evaluation Agent: executes code in isolated sandbox without scoring or persisting submission."""
    session = assessment_sessions.get(req.assessment_id) if req.assessment_id else None
    question = None
    if session and req.question_id:
        question = session["questions"].get(req.question_id)

    # Determine execution language
    lang = (
        req.language
        or (session.get("language") if session else None)
        or (question.language if question else None)
        or "Python"
    )

    result = run_code_sandbox(
        language=lang,
        code=req.code,
        custom_input=req.custom_input,
        question=question,
    )
    return result.model_dump()


@app.post("/assessment/submit")
async def submit_assessment(req: ExecutionRequest):
    """Code Evaluation Agent + Interview Feedback Agent: evaluates submission and test cases."""
    session = assessment_sessions.get(req.assessment_id)
    if not session:
        raise HTTPException(status_code=404, detail="Assessment session not found or expired.")

    question = session["questions"].get(req.question_id)
    if not question:
        raise HTTPException(status_code=404, detail="Question not found.")

    # Safe fallback if is_test_run is set
    if req.is_test_run:
        lang = req.language or session.get("language") or question.language
        run_res = run_code_sandbox(
            language=lang,
            code=req.code,
            custom_input=req.custom_input,
            question=question,
        )
        return run_res.model_dump()

    # Code Evaluation Agent executes code or evaluates MCQ / text answer
    lang = req.language or session.get("language") or question.language
    result = execute_question(
        lang,
        question,
        code=req.code,
        selected_option=req.selected_option,
        text_answer=req.text_answer,
    )

    # Store result in session
    session["results"][question.id] = result
    return result.model_dump()


@app.get("/compiler/languages")
async def compiler_languages():
    """Return execution runtime availability for all supported languages."""
    from assessment import KNOWN_PROGRAMMING_LANGUAGES
    status_list = []
    for lang in KNOWN_PROGRAMMING_LANGUAGES:
        info = check_runtime_support(lang)
        status_list.append({
            "language": lang,
            "supported": info["supported"],
            "message": info["message"],
            "engine": info.get("engine", "Execution Engine"),
        })
    return {"languages": status_list}


@app.get("/assessment/{assessment_id}/results")
async def assessment_results(
    assessment_id: str,
    user: dict[str, Any] | None = Depends(get_user_from_request),
):
    """Performance Insights Agent: synthesizes complete results, readiness rating, and roadmap."""
    session = assessment_sessions.get(assessment_id)
    if not session:
        raise HTTPException(status_code=404, detail="Assessment session not found or expired.")

    question_scores = []
    results_summary = []
    for q_id, question in session["questions"].items():
        res = session["results"].get(q_id)
        score = res.score if res else 0
        question_scores.append({
            "question_id": q_id,
            "title": question.title,
            "category": question.category,
            "topic": question.topic,
            "score": score,
            "skills_tested": question.skills_tested,
            "feedback": res.feedback if res else "Not attempted",
        })
        results_summary.append({
            "title": question.title,
            "topic": question.topic,
            "score": score,
            "passed": res.passed_tests if res else 0,
            "total": res.total_tests if res else 1,
        })

    total_q = len(question_scores)
    final_score = round(sum(q["score"] for q in question_scores) / total_q) if total_q else 0

    # Call Performance Insights Agent
    insights = await orchestrator.generate_performance_insights(
        assessment_id=assessment_id,
        category=session.get("category", "coding"),
        language=session.get("language"),
        difficulty=session.get("difficulty", "medium"),
        results_summary=results_summary,
        overall_score=final_score,
    )

    # Persist in user's test history if candidate is logged in
    if user:
        auth.save_test_history(
            user_id=user["id"],
            assessment_id=assessment_id,
            category=session.get("category", "coding"),
            language=session.get("language"),
            difficulty=session.get("difficulty", "medium"),
            score=final_score,
            feedback=insights.get("readiness_verdict", ""),
        )

    return {
        "assessment_id": assessment_id,
        "category": session.get("category"),
        "language": session.get("language"),
        "difficulty": session.get("difficulty"),
        "final_score": final_score,
        "question_scores": question_scores,
        "insights": insights,
        "resume_skills": session.get("skills", []),
    }


@app.get("/health")
async def health():
    """Service health and deployment check."""
    return {"status": "ok", "service": "InterviewIQ", "model": MODEL_NAME}


if __name__ == "__main__":
    import uvicorn

    logger.info("Starting InterviewIQ on http://localhost:8000")
    uvicorn.run("webapp:app", host="0.0.0.0", port=8000, reload=False)
