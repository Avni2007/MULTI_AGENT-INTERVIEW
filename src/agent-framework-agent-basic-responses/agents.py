"""Microsoft Foundry Multi-Agent System for InterviewIQ.

Contains definitions, system prompts, and orchestrator for the 7 logical agents:
1. Resume Intelligence Agent
2. Adaptive Test Planner
3. Question Forge Agent
4. Code Evaluation Agent
5. Interview Feedback Agent
6. Performance Insights Agent
7. InterviewIQ Orchestrator
"""

from __future__ import annotations

import json
import logging
import os
import re
import textwrap
from typing import Any

from agent_framework import Agent
from agent_framework.foundry import FoundryChatClient
from azure.identity import DefaultAzureCredential

from assessment import (
    AssessmentQuestion,
    AssessmentQuestionSet,
    ExecutionResult,
    canonical_language,
    execute_question,
)

logger = logging.getLogger("interviewiq-agents")


# ─────────────────────────────────────────────────────────────────────────────
# Prompts for Foundry Agents
# ─────────────────────────────────────────────────────────────────────────────

RESUME_INTELLIGENCE_INSTRUCTIONS = textwrap.dedent("""\
    You are the Resume Intelligence Agent for InterviewIQ.
    Analyze the candidate's resume using ONLY evidence found in the provided resume text.

    SCORING RUBRIC (total = 100):
      Structure       /10  — Logical sections, formatting, flow
      Skills          /15  — Relevance, variety, and depth of technical/soft skills
      Experience      /20  — Roles, responsibilities, tenure, quantifiable impact
      Projects        /15  — Technical complexity, technologies used, outcomes
      Achievements    /10  — Awards, certifications, quantifiable wins
      Education       /10  — Degrees, relevant coursework, institutions
      Job Alignment   /15  — Fit against provided job description (0 if none)
      Clarity & Lang  /5   — Writing conciseness, grammar, tone

    RULES:
    - Never invent skills, experience, qualifications, or metrics.
    - If information is absent, state "Not found".
    - Distinguish programming languages from frameworks and libraries.
    - Return ONLY valid JSON (no markdown fences, no explanatory text).

    OUTPUT FORMAT (strict JSON):
    {
      "overall_score": <int 0-100>,
      "category_scores": {
        "structure":        {"score": <0-10>,  "reason": "<string>"},
        "skills":           {"score": <0-15>,  "reason": "<string>"},
        "experience":       {"score": <0-20>,  "reason": "<string>"},
        "projects":         {"score": <0-15>,  "reason": "<string>"},
        "achievements":     {"score": <0-10>,  "reason": "<string>"},
        "education":        {"score": <0-10>,  "reason": "<string>"},
        "job_alignment":    {"score": <0-15>,  "reason": "<string>"},
        "clarity_language": {"score": <0-5>,   "reason": "<string>"}
      },
      "strengths":          ["<string>", ...],
      "improvements":       ["<string>", ...],
      "missing_information":["<string>", ...],
      "weak_bullets":       [{"original": "<string>", "improved": "<string>"}, ...],
      "job_matches":        ["<string>", ...],
      "job_gaps":           ["<string>", ...]
    }
""")

ADAPTIVE_TEST_PLANNER_INSTRUCTIONS = textwrap.dedent("""\
    You are the Adaptive Test Planner for InterviewIQ.
    Your responsibility is to formulate a structured, balanced test plan tailored
    to the candidate's resume and selected test settings.

    Validate that:
    1. The requested category is supported: coding, dsa, core_cs, aptitude, resume_interview.
    2. For coding and dsa, the requested language MUST match one of the candidate's extracted languages.
    3. The difficulty (easy, medium, hard) appropriately governs topic complexity.

    Return ONLY valid JSON matching this schema:
    {
      "category": "<string>",
      "language": "<string or null>",
      "difficulty": "easy|medium|hard",
      "question_count": <int>,
      "duration_minutes": <int>,
      "topics_to_cover": ["<string>", ...],
      "focus_rationale": "<string>"
    }
""")

QUESTION_FORGE_INSTRUCTIONS = textwrap.dedent("""\
    You are the Question Forge Agent for InterviewIQ.
    Generate a complete, high-quality assessment matching the supplied test specification.

    CRITICAL REQUIREMENTS:
    1. For category 'coding':
       - Generate programming questions testing language-specific syntax, idioms, and standard libraries.
       - Questions MUST be relevant to the selected language (e.g. Python-specific, Java-specific, C++-specific).
       - question_type MUST be "coding".
       - Every question MUST include:
         * starter_code: idiomatic entry point that reads from stdin and prints to stdout.
         * visible_tests: at least 1 runnable test case with 'input' and 'expected_output'.
         * hidden_tests: at least 1 runnable test case with 'input' and 'expected_output'.
       - Never return empty visible_tests or hidden_tests for coding questions!

    2. For category 'dsa':
       - Generate algorithmic questions (Arrays, Strings, Trees, Graphs, DP, Two Pointers, Hashing, etc.).
       - Code and starter code MUST match the selected programming language.
       - question_type MUST be "coding".
       - Every question MUST include runnable visible_tests and hidden_tests.

    3. For category 'core_cs':
       - Test OOP, DBMS, Operating Systems, Computer Networks, or Software Engineering.
       - question_type MUST be "mcq".
       - Include 4 distinct 'options' (e.g. ["A) ...", "B) ...", "C) ...", "D) ..."]).
       - 'correct_option': "A", "B", "C", or "D".
       - 'explanation': clear, conceptual reason why the answer is correct.

    4. For category 'aptitude':
       - Test Quantitative Aptitude, Logical Reasoning, or Verbal Ability.
       - question_type MUST be "mcq".
       - Include 4 options, 'correct_option', and 'explanation'.

    5. For category 'resume_interview':
       - Generate in-depth behavioral and technical questions directly grounded in candidate's
         ACTUAL projects, skills, and experience provided in the prompt.
       - DO NOT invent projects, employers, or technologies not present in the prompt.
       - question_type MUST be "interview_text".
       - Include 'evaluation_criteria' (e.g. ["STAR method", "System architecture", "Quantifiable metrics"]).

    OUTPUT FORMAT: Return ONLY valid JSON with this shape:
    {
      "category": "<category>",
      "language": "<language or null>",
      "difficulty": "<easy|medium|hard>",
      "questions": [
        {
          "id": "q1",
          "category": "<category>",
          "question_type": "coding|mcq|interview_text",
          "language": "<language or null>",
          "topic": "<string>",
          "title": "<string>",
          "difficulty": "easy|medium|hard",
          "problem_statement": "<string>",
          "input_description": "<string>",
          "output_description": "<string>",
          "examples": [{"input": "<string>", "output": "<string>", "explanation": "<string>"}],
          "constraints": ["<string>"],
          "starter_code": "<string>",
          "skills_tested": ["<string>"],
          "visible_tests": [{"input": "<string>", "expected_output": "<string>"}],
          "hidden_tests": [{"input": "<string>", "expected_output": "<string>"}],
          "options": ["A) ...", "B) ...", "C) ...", "D) ..."],
          "correct_option": "A|B|C|D",
          "explanation": "<string>",
          "evaluation_criteria": ["<string>"]
        }
      ]
    }
""")

INTERVIEW_FEEDBACK_INSTRUCTIONS = textwrap.dedent("""\
    You are the Interview Feedback Agent for InterviewIQ.
    Review candidate submissions against the question requirements.
    Provide constructive, actionable feedback, highlighting strengths, edge cases,
    and optimization opportunities. Return JSON:
    {
      "score": <int 0-100>,
      "strengths": ["<string>", ...],
      "improvements": ["<string>", ...],
      "summary": "<string>"
    }
""")

PERFORMANCE_INSIGHTS_INSTRUCTIONS = textwrap.dedent("""\
    You are the Performance Insights Agent for InterviewIQ.
    Analyze the full assessment performance based on actual submitted results.
    Never fabricate scores. Group results by topic, highlight strengths, areas for growth,
    and generate a personalized preparation roadmap.

    Return JSON:
    {
      "readiness_score": <int 0-100>,
      "readiness_verdict": "Interview Ready | Proficient | Developing | Needs Practice",
      "topic_breakdown": [{"topic": "<string>", "proficiency": "<string>", "score": <int>}],
      "key_strengths": ["<string>", ...],
      "priority_improvements": ["<string>", ...],
      "next_steps_roadmap": ["<string>", ...]
    }
""")


# ─────────────────────────────────────────────────────────────────────────────
# JSON Parsing Helper
# ─────────────────────────────────────────────────────────────────────────────

def parse_model_json(raw: str) -> dict[str, Any]:
    """Extract and parse JSON object from agent response string."""
    cleaned = raw.strip()
    if cleaned.startswith("```"):
        cleaned = re.sub(r"^```[a-zA-Z]*\n?", "", cleaned)
        cleaned = re.sub(r"\n?```$", "", cleaned.rstrip())

    # Locate first { and last }
    start = cleaned.find("{")
    end = cleaned.rfind("}")
    if start != -1 and end != -1 and end > start:
        cleaned = cleaned[start : end + 1]

    return json.loads(cleaned)


# ─────────────────────────────────────────────────────────────────────────────
# Agent Factory & Orchestrator
# ─────────────────────────────────────────────────────────────────────────────

class InterviewIQOrchestrator:
    """Coordinates the 7 Microsoft Foundry agents for the InterviewIQ platform."""

    def __init__(self, foundry_client: FoundryChatClient) -> None:
        self.foundry_client = foundry_client

        # 1. Resume Intelligence Agent
        self.resume_agent = Agent(
            client=foundry_client,
            instructions=RESUME_INTELLIGENCE_INSTRUCTIONS,
            default_options={"store": False},
        )

        # 2. Adaptive Test Planner
        self.planner_agent = Agent(
            client=foundry_client,
            instructions=ADAPTIVE_TEST_PLANNER_INSTRUCTIONS,
            default_options={"store": False},
        )

        # 3. Question Forge Agent
        self.forge_agent = Agent(
            client=foundry_client,
            instructions=QUESTION_FORGE_INSTRUCTIONS,
            default_options={"store": False},
        )

        # 5. Interview Feedback Agent
        self.feedback_agent = Agent(
            client=foundry_client,
            instructions=INTERVIEW_FEEDBACK_INSTRUCTIONS,
            default_options={"store": False},
        )

        # 6. Performance Insights Agent
        self.insights_agent = Agent(
            client=foundry_client,
            instructions=PERFORMANCE_INSIGHTS_INSTRUCTIONS,
            default_options={"store": False},
        )

    async def run_resume_analysis(self, resume_text: str, job_description: str | None = None) -> dict[str, Any]:
        """Orchestrate Resume Intelligence Agent execution."""
        prompt = f"RESUME TEXT:\n{resume_text}\n\n"
        if job_description and job_description.strip():
            prompt += f"JOB DESCRIPTION:\n{job_description.strip()[:4000]}\n"
        else:
            prompt += "No job description provided — set job_alignment score to 0 with reason 'No job description provided'.\n"

        logger.info("Resume Intelligence Agent running...")
        resp = await self.resume_agent.run(prompt)
        text = resp.text if hasattr(resp, "text") else str(resp)
        return parse_model_json(text)

    async def plan_assessment(
        self,
        candidate_context: dict[str, Any],
        category: str,
        language: str | None,
        difficulty: str,
        question_count: int = 5,
        duration_minutes: int = 45,
    ) -> dict[str, Any]:
        """Orchestrate Adaptive Test Planner execution."""
        payload = {
            "requested_category": category,
            "requested_language": canonical_language(language) or language,
            "requested_difficulty": difficulty,
            "question_count": question_count,
            "duration_minutes": duration_minutes,
            "candidate_languages": candidate_context.get("supported_languages", []),
            "candidate_skills": candidate_context.get("detected_skills", []),
            "candidate_projects": candidate_context.get("projects", []),
        }
        logger.info("Adaptive Test Planner formulating plan...")
        resp = await self.planner_agent.run(json.dumps(payload, ensure_ascii=False))
        text = resp.text if hasattr(resp, "text") else str(resp)
        return parse_model_json(text)

    async def forge_questions(
        self,
        plan: dict[str, Any],
        candidate_context: dict[str, Any],
    ) -> AssessmentQuestionSet:
        """Orchestrate Question Forge Agent execution."""
        payload = {
            "test_plan": plan,
            "candidate_languages": candidate_context.get("supported_languages", []),
            "candidate_skills": candidate_context.get("detected_skills", []),
            "candidate_projects": candidate_context.get("projects", []),
            "instruction": "Generate questions strictly aligned to the test plan and candidate context.",
        }
        logger.info("Question Forge Agent generating questions...")
        resp = await self.forge_agent.run(json.dumps(payload, ensure_ascii=False))
        text = resp.text if hasattr(resp, "text") else str(resp)
        parsed = parse_model_json(text)

        # Validate through Pydantic
        question_set = AssessmentQuestionSet.model_validate(parsed)
        return question_set

    async def generate_feedback(self, question: AssessmentQuestion, user_submission: str, execution_result: ExecutionResult) -> dict[str, Any]:
        """Orchestrate Interview Feedback Agent execution."""
        payload = {
            "question_title": question.title,
            "question_type": question.question_type,
            "problem_statement": question.problem_statement,
            "user_submission": user_submission,
            "execution_score": execution_result.score,
            "execution_feedback": execution_result.feedback,
            "compilation_error": execution_result.compilation_error,
            "runtime_error": execution_result.runtime_error,
        }
        logger.info("Interview Feedback Agent evaluating submission...")
        resp = await self.feedback_agent.run(json.dumps(payload, ensure_ascii=False))
        text = resp.text if hasattr(resp, "text") else str(resp)
        try:
            return parse_model_json(text)
        except Exception:
            return {
                "score": execution_result.score,
                "strengths": ["Completed submission"],
                "improvements": ["Review edge cases"],
                "summary": execution_result.feedback,
            }

    async def generate_performance_insights(
        self,
        assessment_id: str,
        category: str,
        language: str | None,
        difficulty: str,
        results_summary: list[dict[str, Any]],
        overall_score: int,
    ) -> dict[str, Any]:
        """Orchestrate Performance Insights Agent execution."""
        payload = {
            "assessment_id": assessment_id,
            "category": category,
            "language": language,
            "difficulty": difficulty,
            "overall_score": overall_score,
            "question_results": results_summary,
        }
        logger.info("Performance Insights Agent synthesizing results...")
        resp = await self.insights_agent.run(json.dumps(payload, ensure_ascii=False))
        text = resp.text if hasattr(resp, "text") else str(resp)
        try:
            return parse_model_json(text)
        except Exception:
            return {
                "readiness_score": overall_score,
                "readiness_verdict": "Proficient" if overall_score >= 70 else "Developing",
                "topic_breakdown": [{"topic": category, "proficiency": "Good", "score": overall_score}],
                "key_strengths": ["Completed assessment"],
                "priority_improvements": ["Practice language-specific edge cases"],
                "next_steps_roadmap": ["Target weaker topics and practice with timed tests"],
            }
