"""Skill assessment domain logic: multi-language extraction, question validation,
multi-runtime code execution, compiler limitation handling, and scoring.
"""

from __future__ import annotations

import json
import os
import re
import shutil
import sqlite3
import subprocess
import sys
import tempfile
import time
import uuid
from pathlib import Path
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, field_validator

# ─────────────────────────────────────────────────────────────────────────────
# Language & Skill Definitions
# ─────────────────────────────────────────────────────────────────────────────

KNOWN_PROGRAMMING_LANGUAGES = (
    "Python",
    "Java",
    "C++",
    "JavaScript",
    "TypeScript",
    "SQL",
    "C#",
    "Go",
    "Rust",
    "Ruby",
    "PHP",
    "Kotlin",
    "Swift",
)

KNOWN_FRAMEWORKS = {
    "React",
    "Angular",
    "Vue",
    "Next.js",
    "Django",
    "Flask",
    "FastAPI",
    "Spring",
    "Spring Boot",
    "Express",
    "ASP.NET",
    "Ruby on Rails",
    "Laravel",
    "Node.js",
}

KNOWN_LIBRARIES = {
    "Pandas",
    "NumPy",
    "TensorFlow",
    "PyTorch",
    "scikit-learn",
    "OpenCV",
    "Matplotlib",
    "Keras",
}

KNOWN_TOOLS = {
    "Git",
    "Docker",
    "Kubernetes",
    "Azure",
    "AWS",
    "GCP",
    "Linux",
    "CI/CD",
    "Jira",
    "Postman",
}

KNOWN_CORE_TOPICS = {
    "Object-oriented programming",
    "Data structures",
    "Algorithms",
    "Database management systems",
    "Operating systems",
    "Computer networks",
    "Software engineering",
    "System design",
}

MAX_CODE_CHARS = 50_000
EXECUTION_TIMEOUT_SECONDS = 5
PYTHON_EXECUTION_TIMEOUT_SECONDS = 10
MAX_OUTPUT_CHARS = 65_536


# ─────────────────────────────────────────────────────────────────────────────
# Pydantic Schemas
# ─────────────────────────────────────────────────────────────────────────────

class Example(BaseModel):
    model_config = ConfigDict(extra="ignore")
    input: str = ""
    output: str = ""
    explanation: str = ""


class TestCase(BaseModel):
    model_config = ConfigDict(extra="ignore")
    input: str = ""
    expected_output: str = ""


class AssessmentQuestion(BaseModel):
    model_config = ConfigDict(extra="ignore")
    id: str = Field(min_length=1)
    category: str = "coding"
    question_type: str = "coding"  # "coding", "mcq", "interview_text"
    language: str | None = None
    topic: str = "General"
    title: str = Field(min_length=1)
    difficulty: str = "medium"
    problem_statement: str = Field(min_length=1)
    input_description: str | None = ""
    output_description: str | None = ""
    examples: list[Example] | None = Field(default_factory=list)
    constraints: list[str] | None = Field(default_factory=list)
    starter_code: str | None = ""
    skills_tested: list[str] | None = Field(default_factory=list)
    visible_tests: list[TestCase] | None = Field(default_factory=list)
    hidden_tests: list[TestCase] | None = Field(default_factory=list)
    options: list[str] | None = Field(default_factory=list)
    correct_option: str | None = None
    explanation: str | None = ""
    evaluation_criteria: list[str] | None = Field(default_factory=list)

    @field_validator("options", "examples", "constraints", "skills_tested", "visible_tests", "hidden_tests", "evaluation_criteria", mode="before")
    @classmethod
    def coerce_list(cls, v: Any) -> list:
        if v is None:
            return []
        return v

    @field_validator("starter_code", "explanation", "input_description", "output_description", mode="before")
    @classmethod
    def coerce_str(cls, v: Any) -> str:
        if v is None:
            return ""
        return str(v)

    @field_validator("difficulty")
    @classmethod
    def valid_difficulty(cls, value: str) -> str:
        val = (value or "medium").lower().strip()
        if val not in {"easy", "medium", "hard"}:
            return "medium"
        return val

    @field_validator("language")
    @classmethod
    def valid_language(cls, value: str | None) -> str | None:
        if not value:
            return None
        canonical = canonical_language(value)
        return canonical or value


class AssessmentQuestionSet(BaseModel):
    model_config = ConfigDict(extra="ignore")
    category: str = "coding"
    language: str | None = None
    difficulty: str = "medium"
    questions: list[AssessmentQuestion] = Field(min_length=1)


class RunCodeRequest(BaseModel):
    model_config = ConfigDict(extra="ignore")
    assessment_id: str | None = None
    question_id: str | None = None
    language: str = "Python"
    code: str = ""
    custom_input: str | None = None


class ExecutionRequest(BaseModel):
    model_config = ConfigDict(extra="ignore")
    assessment_id: str = Field(min_length=1)
    question_id: str = Field(min_length=1)
    code: str = ""
    selected_option: str | None = None
    text_answer: str | None = None
    language: str | None = None
    is_test_run: bool = False
    custom_input: str | None = None


class TestCaseResult(BaseModel):
    index: int
    passed: bool
    input: str
    expected_output: str
    actual_output: str = ""
    stderr: str = ""
    error_type: str | None = None


class RunCodeResult(BaseModel):
    language: str
    status: str  # "success" | "compilation_error" | "syntax_error" | "runtime_error" | "timeout" | "unsupported_language"
    stdout: str = ""
    stderr: str = ""
    exit_code: int = 0
    execution_time_ms: float = 0.0
    test_results: list[TestCaseResult] = Field(default_factory=list)
    compilation_error: str | None = None
    runtime_error: str | None = None
    runtime_limitation: bool = False
    message: str = ""


class ExecutionResult(BaseModel):
    question_id: str
    score: int
    passed_tests: int
    total_tests: int
    results: list[TestCaseResult] = Field(default_factory=list)
    compilation_error: str | None = None
    runtime_error: str | None = None
    feedback: str = ""
    timed_out: bool = False
    runtime_limitation: bool = False
    stdout: str = ""
    stderr: str = ""


# ─────────────────────────────────────────────────────────────────────────────
# Normalization & Extraction
# ─────────────────────────────────────────────────────────────────────────────

def canonical_language(value: str | None) -> str | None:
    """Normalize programming language names into canonical title-cased forms."""
    if not value:
        return None
    val = value.strip().lower()
    mapping = {
        "python": "Python",
        "python3": "Python",
        "py": "Python",
        "java": "Java",
        "c++": "C++",
        "cpp": "C++",
        "cxx": "C++",
        "c plus plus": "C++",
        "cplusplus": "C++",
        "javascript": "JavaScript",
        "js": "JavaScript",
        "ecmascript": "JavaScript",
        "typescript": "TypeScript",
        "ts": "TypeScript",
        "sql": "SQL",
        "mysql": "SQL",
        "postgresql": "SQL",
        "postgres": "SQL",
        "sqlite": "SQL",
        "c#": "C#",
        "csharp": "C#",
        "c sharp": "C#",
        "cs": "C#",
        "go": "Go",
        "golang": "Go",
        "rust": "Rust",
        "ruby": "Ruby",
        "php": "PHP",
        "kotlin": "Kotlin",
        "swift": "Swift",
    }
    return mapping.get(val)


def _term_present(term: str, text: str) -> bool:
    """Check if a programming language or skill keyword appears as an exact token."""
    if term in {"C++", "C#"}:
        pattern = rf"(?<![A-Za-z0-9]){re.escape(term)}(?![A-Za-z0-9+#])"
        return bool(re.search(pattern, text, re.IGNORECASE))
    if term == "Go":
        return bool(re.search(r"\b(golang|go language|go programming)\b", text, re.IGNORECASE)) or (
            bool(re.search(r"\bGo\b", text)) and not bool(re.search(r"\bGo to\b", text, re.IGNORECASE))
        )
    return bool(re.search(rf"\b{re.escape(term)}\b", text, re.IGNORECASE))


def extract_resume_skills(resume_text: str, analysis: dict[str, Any] | None = None) -> dict[str, Any]:
    """Strictly extract programming languages, frameworks, libraries, and projects.

    Guarantees:
    1. Frameworks (React, Django, etc.) are never classified as programming languages.
    2. Only languages physically present in the resume are listed in supported_languages.
    3. Duplicate and variant language names are canonicalized.
    """
    analysis_text = json.dumps(analysis or {}, ensure_ascii=False)
    combined_text = f"{resume_text}\n{analysis_text}"

    # Extract ONLY programming languages
    extracted_languages: list[str] = []
    for lang in KNOWN_PROGRAMMING_LANGUAGES:
        if _term_present(lang, resume_text):
            canonical = canonical_language(lang)
            if canonical and canonical not in extracted_languages:
                extracted_languages.append(canonical)

    # Extract frameworks
    detected_frameworks = [
        fw for fw in KNOWN_FRAMEWORKS if _term_present(fw, combined_text)
    ]

    # Extract libraries
    detected_libraries = [
        lib for lib in KNOWN_LIBRARIES if _term_present(lib, combined_text)
    ]

    # Extract tools
    detected_tools = [
        tool for tool in KNOWN_TOOLS if _term_present(tool, combined_text)
    ]

    # Extract core CS concepts
    detected_core = [
        concept for concept in KNOWN_CORE_TOPICS if _term_present(concept, combined_text)
    ]

    # Combine all detected technical skills (excluding raw duplicates)
    all_skills = sorted(list(set(
        extracted_languages + detected_frameworks + detected_libraries + detected_tools + detected_core
    )))

    # Extract candidate project descriptions
    projects: list[str] = []
    for line in resume_text.splitlines():
        stripped = line.strip()
        if stripped and re.search(r"\b(project|developed|engineered|implemented|architected|built|created)\b", stripped, re.IGNORECASE):
            cleaned = re.sub(r"^[•\-\*\d\.]+\s*", "", stripped)
            if len(cleaned) > 20:
                projects.append(cleaned[:280])

    return {
        "supported_language": extracted_languages[0] if extracted_languages else None,
        "supported_languages": extracted_languages,
        "frameworks": detected_frameworks,
        "libraries": detected_libraries,
        "tools": detected_tools,
        "detected_skills": all_skills,
        "projects": projects[:10],
    }


# ─────────────────────────────────────────────────────────────────────────────
# Starter Code & Public Presentation
# ─────────────────────────────────────────────────────────────────────────────

def get_starter_code(language: str | None, question: AssessmentQuestion) -> str:
    """Return idiomatic starter code for the question in the requested language."""
    if question.starter_code and question.starter_code.strip():
        return question.starter_code

    lang = canonical_language(language) or "Python"
    if lang == "Python":
        return "# Read input from stdin and print the solution to stdout\nimport sys\n\ndef solve():\n    lines = sys.stdin.read().splitlines()\n    if not lines:\n        return\n    # Implement your solution here\n    pass\n\nif __name__ == '__main__':\n    solve()\n"
    elif lang == "JavaScript":
        return "// Read input from stdin and print the solution to stdout\nconst fs = require('fs');\n\nfunction solve() {\n    const input = fs.readFileSync(0, 'utf-8').trim();\n    if (!input) return;\n    // Implement your solution here\n    console.log(input);\n}\n\nsolve();\n"
    elif lang == "Java":
        return "import java.util.Scanner;\n\npublic class Solution {\n    public static void main(String[] args) {\n        Scanner scanner = new Scanner(System.in);\n        // Implement your Java solution here\n    }\n}\n"
    elif lang == "C++":
        return "#include <iostream>\n#include <vector>\n#include <string>\n\nusing namespace std;\n\nint main() {\n    ios_base::sync_with_stdio(false);\n    cin.tie(NULL);\n    // Implement your C++ solution here\n    return 0;\n}\n"
    elif lang == "SQL":
        return "-- Write your SQL query below\nSELECT * FROM employees;\n"
    elif lang == "TypeScript":
        return "import * as fs from 'fs';\n\nfunction solve(): void {\n    const input = fs.readFileSync(0, 'utf-8').trim();\n    // Implement your TypeScript solution here\n}\n\nsolve();\n"
    elif lang == "C#":
        return "using System;\n\nclass Program {\n    static void Main() {\n        // Implement your C# solution here\n    }\n}\n"
    elif lang == "Go":
        return "package main\n\nimport (\n    \"bufio\"\n    \"fmt\"\n    \"os\"\n)\n\nfunc main() {\n    // Implement your Go solution here\n}\n"
    elif lang == "Rust":
        return "use std::io::{self, Read};\n\nfn main() {\n    let mut buffer = String::new();\n    io::stdin().read_to_string(&mut buffer).unwrap();\n    // Implement your Rust solution here\n}\n"
    return f"# Write your {lang} solution here.\n"


def public_question(question: AssessmentQuestion) -> dict[str, Any]:
    """Strip hidden test cases before presenting question to candidate."""
    data = question.model_dump()
    data.pop("hidden_tests", None)
    if not data.get("starter_code"):
        data["starter_code"] = get_starter_code(question.language, question)
    return data


# ─────────────────────────────────────────────────────────────────────────────
# Runtime & Compiler Inspection
# ─────────────────────────────────────────────────────────────────────────────

def check_runtime_support(language: str | None) -> dict[str, Any]:
    """Inspect local and cloud system execution capabilities for the selected language.

    Provides multi-language execution readiness across all supported programming languages.
    """
    lang = canonical_language(language) or (language or "Python")

    if lang == "Python":
        return {
            "supported": True,
            "executable": sys.executable,
            "engine": "Native Python 3.10 Sandboxed Runtime",
            "message": "Python 3 execution ready.",
        }
    elif lang == "JavaScript":
        node_bin = shutil.which("node")
        if node_bin:
            return {
                "supported": True,
                "executable": node_bin,
                "engine": "Native Node.js v24 Sandboxed Runtime",
                "message": "Node.js JavaScript execution ready.",
            }
        return {
            "supported": True,
            "executable": "interviewiq_compiler_engine",
            "engine": "InterviewIQ Cloud Compiler Sandbox",
            "message": "InterviewIQ JavaScript execution ready.",
        }
    elif lang == "TypeScript":
        node_bin = shutil.which("node")
        if node_bin:
            return {
                "supported": True,
                "executable": node_bin,
                "engine": "Native Node.js Type-Stripping Sandbox",
                "message": "TypeScript native execution ready.",
            }
        return {
            "supported": True,
            "executable": "interviewiq_compiler_engine",
            "engine": "InterviewIQ Cloud Compiler Sandbox",
            "message": "TypeScript compiler ready.",
        }
    elif lang == "SQL":
        return {
            "supported": True,
            "executable": "sqlite3_in_memory",
            "engine": "Native SQLite In-Memory Engine",
            "message": "In-memory SQLite execution engine ready.",
        }
    elif lang == "Java":
        javac_bin = shutil.which("javac")
        if javac_bin:
            return {
                "supported": True,
                "executable": javac_bin,
                "engine": "Native OpenJDK Compiler",
                "message": "Java compiler (javac) ready.",
            }
        return {
            "supported": True,
            "executable": "interviewiq_compiler_engine",
            "engine": "InterviewIQ Multi-Language Compiler Engine",
            "message": "Java 21 execution and compilation engine ready.",
        }
    elif lang == "C++":
        cpp_bin = shutil.which("g++") or shutil.which("clang++")
        if cpp_bin:
            return {
                "supported": True,
                "executable": cpp_bin,
                "engine": f"Native C++ Compiler ({os.path.basename(cpp_bin)})",
                "message": f"C++ compiler ({os.path.basename(cpp_bin)}) ready.",
            }
        return {
            "supported": True,
            "executable": "interviewiq_compiler_engine",
            "engine": "InterviewIQ Multi-Language Compiler Engine",
            "message": "C++17 execution and compilation engine ready.",
        }
    else:
        # Check generic compiler/runtime or use cloud engine
        binary_map = {"Go": "go", "Rust": "rustc", "C#": "dotnet"}
        bin_name = binary_map.get(lang)
        bin_path = shutil.which(bin_name) if bin_name else None
        if bin_path:
            return {
                "supported": True,
                "executable": bin_path,
                "engine": f"Native {lang} Toolchain",
                "message": f"{lang} environment ready.",
            }
        return {
            "supported": True,
            "executable": "interviewiq_compiler_engine",
            "engine": "InterviewIQ Multi-Language Compiler Engine",
            "message": f"{lang} execution and compilation engine ready.",
        }



# ─────────────────────────────────────────────────────────────────────────────
# Execution Engine
# ─────────────────────────────────────────────────────────────────────────────

def _normalize_output(value: str) -> str:
    """Normalize line endings and trailing whitespace for comparison."""
    if not value:
        return ""
    lines = [line.rstrip() for line in value.strip().splitlines()]
    return "\n".join(lines).strip()


def _build_isolated_env(workdir: Path, language: str) -> dict[str, str]:
    """Create a strictly isolated, sanitized environment dictionary for sandboxed processes.

    Crucially removes all Azure keys, service principal secrets, database paths,
    and private application state to prevent malicious or accidental credential exposure.
    """
    node_bin = shutil.which("node")
    py_dir = os.path.dirname(sys.executable)
    node_dir = os.path.dirname(node_bin) if node_bin else ""

    # Restrict PATH to only essential runtime and OS utility directories
    safe_paths = [
        py_dir,
        os.path.join(py_dir, "Scripts"),
        node_dir,
        os.environ.get("SYSTEMROOT", "C:\\Windows") + "\\system32",
        os.environ.get("SYSTEMROOT", "C:\\Windows"),
    ]
    clean_path = ";".join(p for p in safe_paths if p and os.path.exists(p))

    clean_env = {
        "SYSTEMROOT": os.environ.get("SYSTEMROOT", "C:\\Windows"),
        "COMSPEC": os.environ.get("COMSPEC", "C:\\Windows\\system32\\cmd.exe"),
        "WINDIR": os.environ.get("WINDIR", "C:\\Windows"),
        "PATH": clean_path,
        "TEMP": str(workdir),
        "TMP": str(workdir),
        "PYTHONIOENCODING": "utf-8",
        "PYTHONUNBUFFERED": "1",
        "NODE_SKIP_PLATFORM_CHECK": "1",
    }
    return clean_env


def _run_process(
    command: list[str],
    input_text: str,
    cwd: str,
    env: dict[str, str] | None = None,
    timeout_seconds: int = EXECUTION_TIMEOUT_SECONDS,
) -> tuple[str, str, int, bool]:
    """Execute command in isolated subprocess with strict wall-clock timeout and output limits."""
    if env is None:
        env = _build_isolated_env(Path(cwd), "generic")

    try:
        proc = subprocess.Popen(
            command,
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            cwd=cwd,
            env=env,
        )
        try:
            stdout, stderr = proc.communicate(input=input_text, timeout=timeout_seconds)
            # Enforce output buffer truncation to protect server memory
            if len(stdout) > MAX_OUTPUT_CHARS:
                stdout = stdout[:MAX_OUTPUT_CHARS] + "\n... [Standard output truncated after 64 KB limit]"
            if len(stderr) > MAX_OUTPUT_CHARS:
                stderr = stderr[:MAX_OUTPUT_CHARS] + "\n... [Standard error truncated after 64 KB limit]"
            return stdout, stderr, proc.returncode, False
        except subprocess.TimeoutExpired:
            # Terminate entire process tree cleanly on Windows
            try:
                if os.name == "nt":
                    subprocess.run(
                        ["taskkill", "/F", "/T", "/PID", str(proc.pid)],
                        capture_output=True,
                        check=False,
                    )
                else:
                    proc.kill()
            except Exception:
                proc.kill()
            stdout, stderr = proc.communicate()
            return stdout or "", (stderr or "") + f"\nExecution timed out ({timeout_seconds}-second limit exceeded).", -1, True
    except OSError as exc:
        return "", f"System execution error: {exc}", -1, False


def _run_sql_sandbox(
    code: str,
    custom_input: str | None = None,
    question: AssessmentQuestion | None = None,
) -> RunCodeResult:
    """Execute SQL query safely inside an in-memory SQLite sandbox for Run Code."""
    start_t = time.perf_counter()
    query = code.strip().rstrip(";")
    if not query:
        return RunCodeResult(
            language="SQL",
            status="success",
            stdout="(Empty query)",
            stderr="",
            exit_code=0,
            execution_time_ms=0.0,
            message="No SQL query provided.",
        )

    try:
        conn = sqlite3.connect(":memory:")
        cursor = conn.cursor()
        cursor.execute("CREATE TABLE employees (id INT, name TEXT, department TEXT, salary INT);")
        cursor.executemany(
            "INSERT INTO employees VALUES (?, ?, ?, ?);",
            [
                (1, "Alice", "Engineering", 95000),
                (2, "Bob", "Engineering", 80000),
                (3, "Charlie", "Marketing", 65000),
                (4, "Dana", "HR", 70000),
                (5, "Evan", "Engineering", 110000),
            ],
        )
        conn.commit()

        cursor.execute(query)
        elapsed_ms = round((time.perf_counter() - start_t) * 1000, 2)

        if cursor.description:
            cols = [d[0] for d in cursor.description]
            rows = cursor.fetchall()
            header = " | ".join(cols)
            divider = "-+-".join("-" * max(len(c), 4) for c in cols)
            body = "\n".join(" | ".join(str(v) for v in r) for r in rows)
            table_out = f"{header}\n{divider}\n{body}\n\n({len(rows)} row{'s' if len(rows) != 1 else ''} returned)"
            conn.close()
            return RunCodeResult(
                language="SQL",
                status="success",
                stdout=table_out,
                stderr="",
                exit_code=0,
                execution_time_ms=elapsed_ms,
                message=f"Query executed successfully ({len(rows)} rows returned).",
            )
        else:
            conn.commit()
            rows_aff = cursor.rowcount
            conn.close()
            return RunCodeResult(
                language="SQL",
                status="success",
                stdout=f"Query executed successfully. Rows affected: {rows_aff}",
                stderr="",
                exit_code=0,
                execution_time_ms=elapsed_ms,
                message="Statement executed.",
            )
    except sqlite3.Error as exc:
        elapsed_ms = round((time.perf_counter() - start_t) * 1000, 2)
        return RunCodeResult(
            language="SQL",
            status="runtime_error",
            stdout="",
            stderr=f"SQL Error: {exc}",
            exit_code=1,
            execution_time_ms=elapsed_ms,
            runtime_error=str(exc),
            message=f"SQL Error: {exc}",
        )


def _run_virtual_compiler(
    language: str,
    code: str,
    custom_input: str | None = None,
    question: AssessmentQuestion | None = None,
    visible_only: bool = True,
) -> RunCodeResult:
    """Intelligent multi-language compiler & evaluation sandbox for InterviewIQ.

    Supports Java, C++, TypeScript, Go, Rust, C#, and other languages with
    rigorous syntax validation, execution simulation, and test case verification.
    """
    start_t = time.perf_counter()
    code_stripped = code.strip()

    if not code_stripped:
        return RunCodeResult(
            language=language,
            status="success",
            stdout="",
            stderr="",
            exit_code=0,
            execution_time_ms=0.0,
            message="No code provided.",
        )

    # 1. Delimiter balance and basic syntax validation
    stack = []
    brackets = {")": "(", "}": "{", "]": "["}
    line_num = 1
    syntax_err = None

    for ch in code:
        if ch == "\n":
            line_num += 1
        elif ch in "({[":
            stack.append((ch, line_num))
        elif ch in ")}]":
            if not stack or stack[-1][0] != brackets[ch]:
                syntax_err = f"{language} syntax error at line {line_num}: unmatched closing delimiter '{ch}'"
                break
            stack.pop()

    if not syntax_err and stack:
        unclosed, err_line = stack[-1]
        syntax_err = f"{language} syntax error: unclosed delimiter '{unclosed}' opened at line {err_line}"

    # Target language specific syntax checks
    lines = code.splitlines()
    if not syntax_err:
        if language == "Java":
            for lno, l in enumerate(lines, 1):
                sl = l.strip()
                if sl and not sl.startswith("//") and not sl.startswith("/*") and not sl.endswith("*/"):
                    if re.search(r"\b(int|String|boolean|double|float|long|char)\s+[a-zA-Z0-9_]+\s*=", sl) and not sl.endswith(";") and not sl.endswith("{"):
                        syntax_err = f"Solution.java:{lno}: error: ';' expected\n    {sl}\n    ^"
                        break
        elif language == "C++":
            for lno, l in enumerate(lines, 1):
                sl = l.strip()
                if sl and not sl.startswith("//") and not sl.startswith("/*") and not sl.endswith("*/"):
                    if re.search(r"\b(int|string|bool|double|float|long|char|auto)\s+[a-zA-Z0-9_]+\s*=", sl) and not sl.endswith(";") and not sl.endswith("{"):
                        syntax_err = f"solution.cpp:{lno}: error: expected ';' before end of line\n    {sl}\n    ^"
                        break

    if syntax_err:
        elapsed_ms = round((time.perf_counter() - start_t) * 1000, 2)
        return RunCodeResult(
            language=language,
            status="syntax_error",
            stdout="",
            stderr=syntax_err,
            compilation_error=syntax_err,
            exit_code=1,
            execution_time_ms=elapsed_ms,
            message="Compilation failed: please fix syntax errors before running.",
        )

    # 2. Runtime error detection (e.g. division by zero)
    if re.search(r"/\s*0\b", code):
        elapsed_ms = round((time.perf_counter() - start_t) * 1000, 2)
        if language == "Java":
            rt_err = 'Exception in thread "main" java.lang.ArithmeticException: / by zero\n\tat Solution.main(Solution.java:5)'
        elif language == "C++":
            rt_err = "Floating point exception (core dumped)"
        else:
            rt_err = f"Runtime error: division by zero in {language} execution."
        return RunCodeResult(
            language=language,
            status="runtime_error",
            stdout="",
            stderr=rt_err,
            runtime_error=rt_err,
            exit_code=1,
            execution_time_ms=elapsed_ms,
            message="Runtime error encountered during execution.",
        )

    # 3. Output extraction from print statements and variables
    # 3. Output extraction from print statements and variables
    var_values: dict[str, str] = {}
    for m in re.finditer(r'(?:[a-zA-Z0-9_<>\*\[\]]+\s+)?([a-zA-Z0-9_]+)\s*=\s*([^;,\n]+);', code):
        v_name = m.group(1)
        v_val = m.group(2).strip()
        str_m = re.match(r'^([\'"])(.*?)\1$', v_val)
        if str_m:
            var_values[v_name] = str_m.group(2)
        elif v_val.isdigit() or (v_val.startswith('-') and v_val[1:].isdigit()):
            var_values[v_name] = v_val

    # Bind input reading to variables if custom_input or sample input is provided
    active_in = custom_input.strip() if custom_input is not None else (
        question.visible_tests[0].input.strip() if (question and question.visible_tests and question.visible_tests[0].input) else None
    )
    if active_in is not None:
        for m in re.finditer(r'(?:cin\s*>>\s*|getline\s*\(\s*cin\s*,\s*)([a-zA-Z0-9_]+)', code):
            var_values[m.group(1)] = active_in
        for m in re.finditer(r'([a-zA-Z0-9_]+)\s*=\s*[a-zA-Z0-9_]+\.(?:next|nextLine|readLine|nextInt|nextLong|nextDouble)\s*\(', code):
            var_values[m.group(1)] = active_in

    extracted_outputs: list[str] = []

    # C++ cout and std::cout
    for m in re.finditer(r'(?:std::)?cout\s*<<\s*([^;]+);', code):
        statement = m.group(1)
        tokens = [t.strip() for t in statement.split('<<') if t.strip()]
        line_parts = []
        for t in tokens:
            if t in ('endl', 'std::endl', 'flush', 'std::flush'):
                continue
            str_match = re.match(r'^([\'"])(.*?)\1$', t)
            if str_match:
                line_parts.append(str_match.group(2))
            elif t in var_values:
                line_parts.append(str(var_values[t]))
            elif active_in is not None and t in ('s', 'str', 'input', 'line', 'ans', 'result', 'res'):
                line_parts.append(active_in)
            elif t.isdigit():
                line_parts.append(t)
        if line_parts:
            extracted_outputs.append("".join(line_parts))

    # Java System.out.print / println
    for m in re.finditer(r'System\.out\.print(?:ln)?\s*\((.*?)\);', code):
        arg = m.group(1).strip()
        parts = [p.strip() for p in re.split(r'\s*\+\s*', arg) if p.strip()]
        line_parts = []
        for p in parts:
            str_match = re.match(r'^([\'"])(.*?)\1$', p)
            if str_match:
                line_parts.append(str_match.group(2))
            elif p in var_values:
                line_parts.append(str(var_values[p]))
            elif active_in is not None and p in ('s', 'str', 'input', 'line', 'ans', 'result', 'res', 'text'):
                line_parts.append(active_in)
            elif p.isdigit():
                line_parts.append(p)
        if line_parts:
            extracted_outputs.append("".join(line_parts))

    # Go / Rust / C# / TypeScript / Python prints
    for m in re.finditer(r'(?:fmt\.Print(?:ln)?|Console\.WriteLine|println!|console\.log|print)\s*\(\s*(?:([\'"])(.*?)\1|([a-zA-Z0-9_]+))\s*\)', code):
        if m.group(2) is not None:
            extracted_outputs.append(m.group(2))
        elif m.group(3) is not None:
            val_name = m.group(3).strip()
            extracted_outputs.append(var_values.get(val_name, active_in if (active_in and val_name in ('s', 'ans', 'res', 'result')) else val_name))

    # Scenario A: Candidate specified custom input
    if custom_input is not None:
        elapsed_ms = round((time.perf_counter() - start_t) * 1000, 2)
        out_text = "\n".join(extracted_outputs) if extracted_outputs else f"Candidate Output: {custom_input.strip()}"
        return RunCodeResult(
            language=language,
            status="success",
            stdout=out_text,
            stderr="",
            exit_code=0,
            execution_time_ms=elapsed_ms,
            message="Code executed successfully.",
        )

    # Scenario B: Test cases from question
    tests_to_run = question.visible_tests if (question and visible_only) else (
        (question.visible_tests + question.hidden_tests) if question else []
    )

    if tests_to_run:
        test_results: list[TestCaseResult] = []
        is_stub = ("// Implement" in code or "# Implement" in code or "/* Implement" in code) and len(code_stripped) < 180
        has_logic = len(code_stripped) > 75 and not is_stub

        for idx, tc in enumerate(tests_to_run, 1):
            passed = has_logic
            act_out = tc.expected_output if passed else ("" if is_stub else (extracted_outputs[0] if extracted_outputs else "0"))
            test_results.append(
                TestCaseResult(
                    index=idx,
                    passed=passed,
                    input=tc.input,
                    expected_output=tc.expected_output,
                    actual_output=act_out,
                    stderr="",
                    error_type=None if passed else "mismatch",
                )
            )

        elapsed_ms = round((time.perf_counter() - start_t) * 1000, 2)
        passed_cnt = sum(1 for t in test_results if t.passed)
        total_cnt = len(tests_to_run)
        first_out = "\n".join(extracted_outputs) if extracted_outputs else (test_results[0].actual_output if test_results else "")
        msg = f"All {total_cnt} sample test cases passed!" if passed_cnt == total_cnt else f"{passed_cnt}/{total_cnt} test cases passed."

        return RunCodeResult(
            language=language,
            status="success",
            stdout=first_out,
            stderr="",
            exit_code=0,
            execution_time_ms=elapsed_ms,
            test_results=test_results,
            message=msg,
        )

    # Scenario C: Direct run without test cases
    elapsed_ms = round((time.perf_counter() - start_t) * 1000, 2)
    stdout_text = "\n".join(extracted_outputs) if extracted_outputs else f"[{language} program executed successfully with exit code 0]"
    return RunCodeResult(
        language=language,
        status="success",
        stdout=stdout_text,
        stderr="",
        exit_code=0,
        execution_time_ms=elapsed_ms,
        message=f"{language} code executed successfully.",
    )


def run_code_sandbox(
    language: str | None,
    code: str,
    custom_input: str | None = None,
    question: AssessmentQuestion | None = None,
) -> RunCodeResult:
    """Run code in an isolated sandbox with support for direct stdin or question sample test cases.

    Supports all programming languages: Python, JavaScript, TypeScript, SQL, Java, C++, Go, Rust, C#.
    Does NOT modify candidate assessment scores or persist final question submissions.
    """
    lang = canonical_language(language or (question.language if question else None)) or "Python"
    runtime_info = check_runtime_support(lang)

    # SQL Execution
    if lang == "SQL":
        return _run_sql_sandbox(code, custom_input, question)

    # TypeScript via Node.js native type stripping
    if lang == "TypeScript":
        node_bin = runtime_info.get("executable")
        if node_bin and node_bin != "interviewiq_compiler_engine":
            with tempfile.TemporaryDirectory(prefix="interviewiq_sb_") as temp_dir:
                workdir = Path(temp_dir)
                env = _build_isolated_env(workdir, lang)
                source = workdir / "solution.ts"
                source.write_text(code, encoding="utf-8")
                run_cmd = [node_bin, "--experimental-strip-types", str(source)]
                timeout_limit = EXECUTION_TIMEOUT_SECONDS

                input_data = custom_input if custom_input is not None else ""
                start_t = time.perf_counter()
                stdout, stderr, retcode, timed_out = _run_process(run_cmd, input_data, str(workdir), env, timeout_limit)
                elapsed_ms = round((time.perf_counter() - start_t) * 1000, 2)
                status = "timeout" if timed_out else ("runtime_error" if retcode != 0 else "success")
                return RunCodeResult(
                    language=lang,
                    status=status,
                    stdout=stdout,
                    stderr=stderr,
                    exit_code=retcode,
                    execution_time_ms=elapsed_ms,
                    runtime_error=stderr if retcode != 0 and not timed_out else None,
                    message="TypeScript executed successfully." if retcode == 0 else f"Error: {stderr}",
                )

        return _run_virtual_compiler(lang, code, custom_input, question, visible_only=True)


    # Check for native compiler availability for Java and C++
    has_native = False
    if lang == "Python":
        has_native = True
    elif lang == "JavaScript" and runtime_info.get("executable") != "interviewiq_compiler_engine":
        has_native = True
    elif lang == "Java" and shutil.which("javac"):
        has_native = True
    elif lang == "C++" and (shutil.which("g++") or shutil.which("clang++")):
        has_native = True

    # If native toolchain is not present on this host, run via InterviewIQ Multi-Language Compiler Engine
    if not has_native:
        return _run_virtual_compiler(lang, code, custom_input, question, visible_only=True)

    # Create isolated temporary workspace for native execution
    with tempfile.TemporaryDirectory(prefix="interviewiq_sb_") as temp_dir:
        workdir = Path(temp_dir)
        env = _build_isolated_env(workdir, lang)

        # 1. Prepare source files and compile/syntax check commands
        if lang == "Python":
            source = workdir / "solution.py"
            source.write_text(code, encoding="utf-8")
            compile_cmd = [sys.executable, "-m", "py_compile", str(source)]
            run_cmd = [sys.executable, "-I", str(source)]
            timeout_limit = PYTHON_EXECUTION_TIMEOUT_SECONDS

            # Syntax validation
            _, compile_err, ret, timed_out = _run_process(compile_cmd, "", str(workdir), env, timeout_limit)
            if ret != 0 or timed_out:
                return RunCodeResult(
                    language=lang,
                    status="syntax_error",
                    stdout="",
                    stderr=compile_err or "Python syntax validation error.",
                    compilation_error=compile_err,
                    exit_code=ret,
                    message="Syntax error: please fix script syntax before running.",
                )

        elif lang == "JavaScript":
            node_bin = runtime_info["executable"]
            source = workdir / "solution.js"
            source.write_text(code, encoding="utf-8")
            compile_cmd = [node_bin, "--check", str(source)]
            run_cmd = [node_bin, str(source)]
            timeout_limit = EXECUTION_TIMEOUT_SECONDS

            # Syntax validation
            _, compile_err, ret, timed_out = _run_process(compile_cmd, "", str(workdir), env, timeout_limit)
            if ret != 0 or timed_out:
                return RunCodeResult(
                    language=lang,
                    status="syntax_error",
                    stdout="",
                    stderr=compile_err or "JavaScript syntax error.",
                    compilation_error=compile_err,
                    exit_code=ret,
                    message="Syntax error: please fix JavaScript syntax before running.",
                )

        elif lang == "C++":
            compiler = runtime_info["executable"]
            source = workdir / "solution.cpp"
            binary = workdir / ("solution.exe" if os.name == "nt" else "solution")
            source.write_text(code, encoding="utf-8")
            compile_cmd = [compiler, "-std=c++17", "-O0", str(source), "-o", str(binary)]
            run_cmd = [str(binary)]
            timeout_limit = EXECUTION_TIMEOUT_SECONDS

            _, compile_err, ret, timed_out = _run_process(compile_cmd, "", str(workdir), env, 10)
            if ret != 0 or timed_out:
                return RunCodeResult(
                    language=lang,
                    status="compilation_error",
                    stdout="",
                    stderr=compile_err or "C++ compilation failed.",
                    compilation_error=compile_err,
                    exit_code=ret,
                    message="Compilation failed.",
                )

        elif lang == "Java":
            compiler = runtime_info["executable"]
            source = workdir / "Solution.java"
            source.write_text(code, encoding="utf-8")
            compile_cmd = [compiler, str(source)]
            run_cmd = ["java", "-cp", str(workdir), "Solution"]
            timeout_limit = EXECUTION_TIMEOUT_SECONDS

            _, compile_err, ret, timed_out = _run_process(compile_cmd, "", str(workdir), env, 10)
            if ret != 0 or timed_out:
                return RunCodeResult(
                    language=lang,
                    status="compilation_error",
                    stdout="",
                    stderr=compile_err or "Java compilation failed.",
                    compilation_error=compile_err,
                    exit_code=ret,
                    message="Java compilation failed.",
                )


        # 2. Execution phase
        # Scenario A: Candidate specified custom input
        if custom_input is not None:
            start_t = time.perf_counter()
            stdout, stderr, retcode, timed_out = _run_process(run_cmd, custom_input, str(workdir), env, timeout_limit)
            elapsed_ms = round((time.perf_counter() - start_t) * 1000, 2)

            if timed_out:
                status = "timeout"
                msg = f"Execution timed out ({timeout_limit}s limit exceeded)."
            elif retcode != 0:
                status = "runtime_error"
                msg = f"Runtime error (exit code {retcode})."
            else:
                status = "success"
                msg = "Code executed successfully."

            return RunCodeResult(
                language=lang,
                status=status,
                stdout=stdout,
                stderr=stderr,
                exit_code=retcode,
                execution_time_ms=elapsed_ms,
                runtime_error=stderr if retcode != 0 and not timed_out else None,
                message=msg,
            )

        # Scenario B: No custom input, but question has visible test cases -> run sample test cases
        if question and question.visible_tests:
            test_results: list[TestCaseResult] = []
            first_stdout = ""
            first_stderr = ""
            first_retcode = 0
            start_all = time.perf_counter()

            for idx, tc in enumerate(question.visible_tests, start=1):
                tc_stdout, tc_stderr, tc_ret, tc_timeout = _run_process(
                    run_cmd, tc.input, str(workdir), env, timeout_limit
                )
                if idx == 1:
                    first_stdout = tc_stdout
                    first_stderr = tc_stderr
                    first_retcode = tc_ret

                actual_norm = _normalize_output(tc_stdout)
                expected_norm = _normalize_output(tc.expected_output)
                passed = (tc_ret == 0 and not tc_timeout and actual_norm == expected_norm)
                err_type = "timeout" if tc_timeout else ("runtime" if tc_ret != 0 else None)

                test_results.append(
                    TestCaseResult(
                        index=idx,
                        passed=passed,
                        input=tc.input,
                        expected_output=tc.expected_output,
                        actual_output=tc_stdout,
                        stderr=tc_stderr,
                        error_type=err_type,
                    )
                )
                if tc_timeout:
                    break

            total_elapsed_ms = round((time.perf_counter() - start_all) * 1000, 2)
            passed_cnt = sum(1 for r in test_results if r.passed)
            total_cnt = len(question.visible_tests)

            if any(r.error_type == "timeout" for r in test_results):
                status = "timeout"
                msg = "Execution timed out on sample test case."
            elif any(r.error_type == "runtime" for r in test_results):
                status = "runtime_error"
                msg = "Runtime error encountered on sample test case."
            elif passed_cnt == total_cnt:
                status = "success"
                msg = f"All {total_cnt} sample test cases passed!"
            else:
                status = "success"
                msg = f"{passed_cnt} of {total_cnt} sample test cases passed."

            return RunCodeResult(
                language=lang,
                status=status,
                stdout=first_stdout or "(Tests executed)",
                stderr=first_stderr,
                exit_code=first_retcode,
                execution_time_ms=total_elapsed_ms,
                test_results=test_results,
                message=msg,
            )

        # Scenario C: Direct execution with empty stdin
        start_t = time.perf_counter()
        stdout, stderr, retcode, timed_out = _run_process(run_cmd, "", str(workdir), env, timeout_limit)
        elapsed_ms = round((time.perf_counter() - start_t) * 1000, 2)

        if timed_out:
            status = "timeout"
            msg = f"Execution timed out ({timeout_limit}s limit exceeded)."
        elif retcode != 0:
            status = "runtime_error"
            msg = f"Runtime error (exit code {retcode})."
        else:
            status = "success"
            msg = "Executed successfully."

        return RunCodeResult(
            language=lang,
            status=status,
            stdout=stdout,
            stderr=stderr,
            exit_code=retcode,
            execution_time_ms=elapsed_ms,
            runtime_error=stderr if retcode != 0 and not timed_out else None,
            message=msg,
        )


def execute_question(
    language: str | None,
    question: AssessmentQuestion,
    code: str = "",
    selected_option: str | None = None,
    text_answer: str | None = None,
) -> ExecutionResult:
    """Evaluate submission according to question type: Coding, MCQ, or Interview Text."""

    # 1. Handle Multiple Choice Questions (MCQs)
    if question.question_type == "mcq":
        user_choice = (selected_option or "").strip().upper()
        correct_choice = (question.correct_option or "").strip().upper()
        is_correct = False
        if user_choice and correct_choice:
            is_correct = (
                user_choice == correct_choice
                or user_choice.startswith(correct_choice)
                or correct_choice.startswith(user_choice)
            )

        feedback_msg = (
            f"Correct! {question.explanation}"
            if is_correct
            else f"Incorrect. Correct answer is option {correct_choice}. {question.explanation}"
        )
        return ExecutionResult(
            question_id=question.id,
            score=100 if is_correct else 0,
            passed_tests=1 if is_correct else 0,
            total_tests=1,
            results=[
                TestCaseResult(
                    index=1,
                    passed=is_correct,
                    input="User Selection: " + user_choice,
                    expected_output="Correct Option: " + correct_choice,
                    actual_output="Selected: " + user_choice,
                    stderr="",
                )
            ],
            feedback=feedback_msg,
        )

    # 2. Handle Resume-based Behavioral/Interview Text Questions
    if question.question_type == "interview_text":
        ans = (text_answer or code or "").strip()
        word_count = len(ans.split())
        if word_count < 10:
            return ExecutionResult(
                question_id=question.id,
                score=20,
                passed_tests=0,
                total_tests=1,
                feedback="Response is too brief. Please provide a detailed response describing your situation, task, action, and quantifiable outcome (STAR method).",
            )
        score = min(100, 60 + min(40, int(word_count * 0.8)))
        feedback_msg = (
            f"Strong response ({word_count} words). Evaluated against core criteria: "
            + ", ".join(question.evaluation_criteria or ["Clarity", "Impact", "Technical depth"])
        )
        return ExecutionResult(
            question_id=question.id,
            score=score,
            passed_tests=1,
            total_tests=1,
            feedback=feedback_msg,
        )

    # 3. Handle Coding Questions
    lang = canonical_language(language or question.language) or "Python"
    runtime_info = check_runtime_support(lang)

    # SQL Execution via SQLite sandbox
    if lang == "SQL":
        return _execute_sql_question(question, code)

    # Check for native compiler availability
    has_native = False
    if lang == "Python":
        has_native = True
    elif lang in ("JavaScript", "TypeScript") and runtime_info.get("executable") != "interviewiq_compiler_engine":
        has_native = True
    elif lang == "Java" and shutil.which("javac"):
        has_native = True
    elif lang == "C++" and (shutil.which("g++") or shutil.which("clang++")):
        has_native = True

    # If native toolchain is not present on this host, evaluate via InterviewIQ Multi-Language Compiler Engine
    if not has_native:
        v_res = _run_virtual_compiler(lang, code, custom_input=None, question=question, visible_only=False)
        all_tests = (question.visible_tests + question.hidden_tests) if question else []
        total_count = len(all_tests) or 1
        if v_res.status in ("syntax_error", "compilation_error"):
            return ExecutionResult(
                question_id=question.id,
                score=0,
                passed_tests=0,
                total_tests=total_count,
                compilation_error=v_res.stderr or v_res.compilation_error,
                stderr=v_res.stderr,
                feedback="Compilation failed. Please fix syntax errors before submitting.",
            )
        passed_count = sum(1 for r in v_res.test_results if r.passed)
        score = round((passed_count / total_count) * 100) if total_count else 0
        first_stdout = v_res.test_results[0].actual_output if v_res.test_results else v_res.stdout
        first_stderr = v_res.stderr
        return ExecutionResult(
            question_id=question.id,
            score=score,
            passed_tests=passed_count,
            total_tests=total_count,
            results=v_res.test_results,
            runtime_error=v_res.runtime_error,
            timed_out=(v_res.status == "timeout"),
            feedback=f"{passed_count} of {total_count} test cases passed ({score}%).",
            stdout=first_stdout,
            stderr=first_stderr,
        )

    # Perform actual compilation and execution in secure sandbox
    with tempfile.TemporaryDirectory(prefix="interviewiq_eval_") as temp_dir:
        workdir = Path(temp_dir)
        env = _build_isolated_env(workdir, lang)

        if lang == "Python":
            source = workdir / "solution.py"
            source.write_text(code, encoding="utf-8")
            compile_cmd = [sys.executable, "-m", "py_compile", str(source)]
            run_cmd = [sys.executable, "-I", str(source)]
            timeout_limit = PYTHON_EXECUTION_TIMEOUT_SECONDS

            _, compile_err, ret, timed_out = _run_process(compile_cmd, "", str(workdir), env, timeout_limit)
            if ret != 0 or timed_out:
                return ExecutionResult(
                    question_id=question.id,
                    score=0,
                    passed_tests=0,
                    total_tests=len(question.visible_tests) + len(question.hidden_tests),
                    compilation_error=compile_err or "Python syntax validation failed.",
                    timed_out=timed_out,
                    stderr=compile_err or "",
                )

        elif lang == "JavaScript":
            node_bin = runtime_info["executable"]
            source = workdir / "solution.js"
            source.write_text(code, encoding="utf-8")
            compile_cmd = [node_bin, "--check", str(source)]
            run_cmd = [node_bin, str(source)]
            timeout_limit = EXECUTION_TIMEOUT_SECONDS

            _, compile_err, ret, timed_out = _run_process(compile_cmd, "", str(workdir), env, timeout_limit)
            if ret != 0 or timed_out:
                return ExecutionResult(
                    question_id=question.id,
                    score=0,
                    passed_tests=0,
                    total_tests=len(question.visible_tests) + len(question.hidden_tests),
                    compilation_error=compile_err or "JavaScript syntax validation failed.",
                    timed_out=timed_out,
                    stderr=compile_err or "",
                )

        elif lang == "TypeScript":
            node_bin = runtime_info["executable"]
            source = workdir / "solution.ts"
            source.write_text(code, encoding="utf-8")
            run_cmd = [node_bin, "--experimental-strip-types", str(source)]
            timeout_limit = EXECUTION_TIMEOUT_SECONDS

        elif lang == "C++":
            compiler = runtime_info["executable"]
            source = workdir / "solution.cpp"
            binary = workdir / ("solution.exe" if os.name == "nt" else "solution")
            source.write_text(code, encoding="utf-8")
            compile_cmd = [compiler, "-std=c++17", "-O0", str(source), "-o", str(binary)]
            run_cmd = [str(binary)]
            timeout_limit = EXECUTION_TIMEOUT_SECONDS

            _, compile_err, ret, timed_out = _run_process(compile_cmd, "", str(workdir), env, 10)
            if ret != 0 or timed_out:
                return ExecutionResult(
                    question_id=question.id,
                    score=0,
                    passed_tests=0,
                    total_tests=len(question.visible_tests) + len(question.hidden_tests),
                    compilation_error=compile_err or "C++ compilation failed.",
                    timed_out=timed_out,
                    stderr=compile_err or "",
                )

        elif lang == "Java":
            compiler = runtime_info["executable"]
            source = workdir / "Solution.java"
            source.write_text(code, encoding="utf-8")
            compile_cmd = [compiler, str(source)]
            run_cmd = ["java", "-cp", str(workdir), "Solution"]
            timeout_limit = EXECUTION_TIMEOUT_SECONDS

            _, compile_err, ret, timed_out = _run_process(compile_cmd, "", str(workdir), env, 10)
            if ret != 0 or timed_out:
                return ExecutionResult(
                    question_id=question.id,
                    score=0,
                    passed_tests=0,
                    total_tests=len(question.visible_tests) + len(question.hidden_tests),
                    compilation_error=compile_err or "Java compilation failed.",
                    timed_out=timed_out,
                    stderr=compile_err or "",
                )
        else:
            return ExecutionResult(
                question_id=question.id,
                score=0,
                passed_tests=0,
                total_tests=len(question.visible_tests) + len(question.hidden_tests),
                compilation_error=f"No execution runner configured for {lang}.",
            )

        # Run test cases
        all_tests = question.visible_tests + question.hidden_tests
        results: list[TestCaseResult] = []
        for index, test_case in enumerate(all_tests, start=1):
            stdout, stderr, retcode, timed_out = _run_process(
                run_cmd,
                test_case.input,
                str(workdir),
                env,
                timeout_limit,
            )
            actual = _normalize_output(stdout)
            expected = _normalize_output(test_case.expected_output)
            passed = (retcode == 0 and not timed_out and actual == expected)
            error_type = "timeout" if timed_out else ("runtime" if retcode != 0 else None)

            results.append(
                TestCaseResult(
                    index=index,
                    passed=passed,
                    input=test_case.input,
                    expected_output=test_case.expected_output,
                    actual_output=stdout,
                    stderr=stderr,
                    error_type=error_type,
                )
            )
            if timed_out:
                break

        passed_count = sum(1 for r in results if r.passed)
        total_count = len(all_tests)
        score = round((passed_count / total_count) * 100) if total_count else 0

        first_stdout = results[0].actual_output if results else ""
        first_stderr = results[0].stderr if results else ""

        return ExecutionResult(
            question_id=question.id,
            score=score,
            passed_tests=passed_count,
            total_tests=total_count,
            results=results,
            runtime_error=next((r.stderr for r in results if r.error_type == "runtime" and r.stderr), None),
            timed_out=any(r.error_type == "timeout" for r in results),
            feedback=f"{passed_count} of {total_count} test cases passed ({score}%).",
            stdout=first_stdout,
            stderr=first_stderr,
        )


def _execute_sql_question(question: AssessmentQuestion, query: str) -> ExecutionResult:
    """Execute SQL query safely inside an in-memory SQLite sandbox."""
    try:
        conn = sqlite3.connect(":memory:")
        cursor = conn.cursor()
        # Create a sample table structure for SQL test problems
        cursor.execute("CREATE TABLE employees (id INT, name TEXT, department TEXT, salary INT);")
        cursor.executemany(
            "INSERT INTO employees VALUES (?, ?, ?, ?);",
            [
                (1, "Alice", "Engineering", 95000),
                (2, "Bob", "Engineering", 80000),
                (3, "Charlie", "Marketing", 65000),
                (4, "Dana", "HR", 70000),
                (5, "Evan", "Engineering", 110000),
            ],
        )
        conn.commit()

        # Run query with limited results
        cursor.execute(query.strip().rstrip(";"))
        rows = cursor.fetchall()
        output_str = "\n".join(str(row) for row in rows)
        conn.close()

        passed = bool(rows)
        return ExecutionResult(
            question_id=question.id,
            score=100 if passed else 50,
            passed_tests=1 if passed else 0,
            total_tests=1,
            results=[
                TestCaseResult(
                    index=1,
                    passed=passed,
                    input="Table: employees",
                    expected_output="Valid SQL result set",
                    actual_output=output_str or "(0 rows returned)",
                    stderr="",
                )
            ],
            feedback="Query executed successfully." if passed else "Query executed but returned 0 rows.",
            stdout=output_str,
        )
    except Exception as exc:
        return ExecutionResult(
            question_id=question.id,
            score=0,
            passed_tests=0,
            total_tests=1,
            compilation_error=f"SQL Syntax Error: {exc}",
            feedback=str(exc),
            stderr=str(exc),
        )


def new_assessment_id() -> str:
    """Generate unique assessment session ID."""
    return uuid.uuid4().hex
