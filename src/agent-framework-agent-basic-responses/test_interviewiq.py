"""Comprehensive verification test suite for InterviewIQ.

Validates:
1. Multi-language extraction & normalization (strictly differentiating languages from frameworks)
2. Multi-category assessment question schemas
3. Python native code execution with test cases
4. JavaScript (Node.js) native code execution with test cases
5. Host compiler limitation handling for Java and C++
6. Core CS / Aptitude MCQ evaluation
7. Resume-based interview text evaluation
8. SQLite Authentication (Signup, Login, Sessions, Test History, Logout)
9. FastAPI Web Application routes and health check
"""

from __future__ import annotations

import asyncio
import os
import sys
from pathlib import Path

# Add project root to sys.path
HERE = Path(__file__).parent
sys.path.insert(0, str(HERE))

import auth
import assessment
from assessment import (
    AssessmentQuestion,
    AssessmentQuestionSet,
    Example,
    TestCase,
    canonical_language,
    check_runtime_support,
    execute_question,
    extract_resume_skills,
)


def test_language_normalization():
    print("Testing Language Normalization & Framework Separation...")
    assert canonical_language("python") == "Python"
    assert canonical_language("python3") == "Python"
    assert canonical_language("py") == "Python"
    assert canonical_language("cpp") == "C++"
    assert canonical_language("c++") == "C++"
    assert canonical_language("cplusplus") == "C++"
    assert canonical_language("javascript") == "JavaScript"
    assert canonical_language("js") == "JavaScript"
    assert canonical_language("typescript") == "TypeScript"
    assert canonical_language("java") == "Java"
    assert canonical_language("sql") == "SQL"
    assert canonical_language("c#") == "C#"
    assert canonical_language("golang") == "Go"
    assert canonical_language("rust") == "Rust"

    # Frameworks should return None as programming languages
    assert canonical_language("react") is None
    assert canonical_language("django") is None
    assert canonical_language("fastapi") is None
    print("  -> Passed: Canonicalization correctly distinguishes languages from frameworks.")


def test_resume_extraction():
    print("Testing Resume Extraction...")
    sample_resume = """
    Alex Rivera - Senior Software Engineer
    Technical Skills: Python, Java, C++, JavaScript, TypeScript, SQL, React, Next.js, Django, Docker, Kubernetes, Git
    Experience:
    - Built a high-concurrency microservices platform in Go and Python.
    - Developed reactive dashboard using React and TypeScript with Node.js backend.
    - Optimized relational database queries in PostgreSQL/SQL.
    Projects:
    - Designed and implemented automated algorithmic trading engine in C++ and Python.
    - Architected distributed data processing pipeline using Kafka and Spark.
    """
    extracted = extract_resume_skills(sample_resume)
    langs = extracted["supported_languages"]
    fws = extracted["frameworks"]

    # Verify programming languages extracted
    assert "Python" in langs
    assert "Java" in langs
    assert "C++" in langs
    assert "JavaScript" in langs
    assert "TypeScript" in langs
    assert "SQL" in langs

    # Verify frameworks are segregated and NOT in languages
    assert "React" in fws
    assert "Django" in fws
    assert "React" not in langs
    assert "Django" not in langs
    assert "Docker" not in langs

    # Verify projects extracted
    assert len(extracted["projects"]) >= 2
    print(f"  -> Passed: Extracted {len(langs)} languages: {langs}")
    print(f"  -> Passed: Segregated frameworks: {fws}")


def test_runtime_support_inspection():
    print("Testing Host Runtime Capabilities...")
    py_check = check_runtime_support("Python")
    assert py_check["supported"] is True

    js_check = check_runtime_support("JavaScript")
    assert js_check["supported"] is True, "Node.js should be detected on host"

    sql_check = check_runtime_support("SQL")
    assert sql_check["supported"] is True

    java_check = check_runtime_support("Java")
    assert java_check["supported"] is True
    assert "Engine" in java_check.get("engine", "") or "Java" in java_check.get("message", "")

    cpp_check = check_runtime_support("C++")
    assert cpp_check["supported"] is True
    assert "Engine" in cpp_check.get("engine", "") or "C++" in cpp_check.get("message", "")

    print(f"  -> Passed: Python runtime: {py_check['executable']}")
    print(f"  -> Passed: JavaScript (Node.js) runtime: {js_check['executable']}")
    print(f"  -> Passed: Java engine designation: {java_check.get('engine', java_check['message'])[:60]}...")


def test_python_code_execution():
    print("Testing Python Code Execution...")
    q = AssessmentQuestion(
        id="q_py_1",
        category="coding",
        question_type="coding",
        language="Python",
        title="Multiply Two Numbers",
        difficulty="easy",
        problem_statement="Read two space-separated integers from stdin and print their product.",
        visible_tests=[TestCase(input="4 5", expected_output="20")],
        hidden_tests=[
            TestCase(input="10 15", expected_output="150"),
            TestCase(input="-2 8", expected_output="-16"),
        ],
    )
    solution = """
import sys
parts = sys.stdin.read().split()
if parts:
    print(int(parts[0]) * int(parts[1]))
"""
    result = execute_question("Python", q, code=solution)
    assert result.score == 100
    assert result.passed_tests == 3
    assert result.total_tests == 3
    assert result.compilation_error is None
    print("  -> Passed: Python code execution 3/3 test cases passed (Score: 100/100).")


def test_javascript_code_execution():
    print("Testing JavaScript (Node.js) Code Execution...")
    q = AssessmentQuestion(
        id="q_js_1",
        category="coding",
        question_type="coding",
        language="JavaScript",
        title="Reverse String",
        difficulty="easy",
        problem_statement="Read a string from stdin and print its reverse.",
        visible_tests=[TestCase(input="hello", expected_output="olleh")],
        hidden_tests=[
            TestCase(input="interview", expected_output="weivretni"),
            TestCase(input="foundry", expected_output="yrdnuof"),
        ],
    )
    solution = """
const fs = require('fs');
const input = fs.readFileSync(0, 'utf-8').trim();
console.log(input.split('').reverse().join(''));
"""
    result = execute_question("JavaScript", q, code=solution)
    assert result.score == 100
    assert result.passed_tests == 3
    assert result.total_tests == 3
    assert result.compilation_error is None
    print("  -> Passed: JavaScript (Node.js) execution 3/3 test cases passed (Score: 100/100).")


def test_compiler_limitation_handling():
    print("Testing Multi-Language Compiler Engine (Java & C++)...")
    q_java = AssessmentQuestion(
        id="q_java_1",
        category="coding",
        question_type="coding",
        language="Java",
        title="Java Palindrome",
        difficulty="easy",
        problem_statement="Determine if a string is a palindrome.",
        visible_tests=[TestCase(input="racecar", expected_output="true")],
        hidden_tests=[TestCase(input="hello", expected_output="false")],
    )
    java_solution = """
import java.util.Scanner;
public class Solution {
    public static void main(String[] args) {
        Scanner sc = new Scanner(System.in);
        if (sc.hasNext()) {
            String s = sc.next();
            String rev = new StringBuilder(s).reverse().toString();
            System.out.println(s.equals(rev) ? "true" : "false");
        }
    }
}
"""
    result_java = execute_question("Java", q_java, code=java_solution)
    assert result_java.score == 100, f"Expected 100, got {result_java.score}"
    assert result_java.passed_tests == 2
    assert result_java.compilation_error is None
    print("  -> Passed: Java question execution & test grading in Multi-Language Engine (2/2 passed).")

    q_cpp = AssessmentQuestion(
        id="q_cpp_1",
        category="coding",
        question_type="coding",
        language="C++",
        title="C++ Max Element",
        difficulty="easy",
        problem_statement="Find max element in array.",
        visible_tests=[TestCase(input="3\n1 5 2", expected_output="5")],
        hidden_tests=[],
    )
    # Test syntax error detection
    result_cpp_err = execute_question("C++", q_cpp, code="#include <iostream>\nint main() { broken( }")
    assert result_cpp_err.score == 0
    assert result_cpp_err.compilation_error is not None
    print("  -> Passed: C++ syntax error detection verified in Multi-Language Engine.")


def test_mcq_evaluation():
    print("Testing Core CS & Aptitude MCQ Evaluation...")
    q_mcq = AssessmentQuestion(
        id="q_mcq_1",
        category="core_cs",
        question_type="mcq",
        title="Database ACID Properties",
        difficulty="medium",
        problem_statement="Which property ensures database transactions are permanently saved even across system crashes?",
        options=["A) Atomicity", "B) Consistency", "C) Isolation", "D) Durability"],
        correct_option="D",
        explanation="Durability ensures that once a transaction commits, its effects survive power loss or crashes.",
    )
    res_correct = execute_question(None, q_mcq, selected_option="D")
    assert res_correct.score == 100
    assert "Correct!" in res_correct.feedback

    res_wrong = execute_question(None, q_mcq, selected_option="A")
    assert res_wrong.score == 0
    assert "Incorrect" in res_wrong.feedback
    print("  -> Passed: MCQ evaluation verifies correct and incorrect option selections.")


def test_interview_text_evaluation():
    print("Testing Resume-Based Behavioral Interview Evaluation...")
    q_interview = AssessmentQuestion(
        id="q_int_1",
        category="resume_interview",
        question_type="interview_text",
        title="Architectural Tradeoff Discussion",
        difficulty="medium",
        problem_statement="Describe the architectural tradeoffs you made when developing the distributed message queue project mentioned on your resume.",
        evaluation_criteria=["STAR method", "System architecture", "Quantifiable metrics"],
    )
    response_text = (
        "In our distributed message queue project, we needed sub-millisecond latency while guaranteeing at-least-once delivery. "
        "We chose an append-only commit log partitioned by hash key, paired with zero-copy network transfer using sendfile. "
        "This allowed us to achieve 150,000 messages/sec with p99 latency under 2ms, trading off memory overhead for raw throughput."
    )
    res = execute_question(None, q_interview, text_answer=response_text)
    assert res.score >= 70
    assert "Strong response" in res.feedback
    print(f"  -> Passed: Interview text evaluated against criteria (Score: {res.score}/100).")


def test_auth_and_sessions():
    print("Testing Candidate Authentication & Sessions...")
    auth.init_db()
    email = f"candidate_{os.urandom(4).hex()}@example.com"
    registered = auth.register_user("Maria Garcia", email, "secret123")
    assert registered["name"] == "Maria Garcia"
    assert registered["email"] == email

    authenticated = auth.authenticate_user(email, "secret123")
    assert authenticated is not None
    assert authenticated["id"] == registered["id"]

    wrong_auth = auth.authenticate_user(email, "wrongpassword")
    assert wrong_auth is None

    session_token = auth.create_session(authenticated["id"])
    assert session_token is not None

    session_user = auth.get_user_by_session(session_token)
    assert session_user["email"] == email

    # Test saving history
    auth.save_test_history(
        user_id=authenticated["id"],
        assessment_id="test_session_42",
        category="coding",
        language="Python",
        difficulty="medium",
        score=95,
        feedback="Proficient",
    )
    history = auth.get_user_test_history(authenticated["id"])
    assert len(history) == 1
    assert history[0]["score"] == 95
    assert history[0]["language"] == "Python"

    # Logout
    assert auth.delete_session(session_token) is True
    assert auth.get_user_by_session(session_token) is None
    print("  -> Passed: Candidate registration, authentication, sessions, history, and logout verified.")


def test_fastapi_app_routes():
    print("Testing FastAPI Application Routes via TestClient...")
    from fastapi.testclient import TestClient
    import webapp

    client = TestClient(webapp.app)

    # 1. Health route
    health_resp = client.get("/health")
    assert health_resp.status_code == 200
    assert health_resp.json()["status"] == "ok"

    # 2. UI routes
    assert client.get("/").status_code == 200
    assert client.get("/resume-analysis").status_code == 200
    assert client.get("/mock-tests").status_code == 200
    assert client.get("/results").status_code == 200
    assert client.get("/dashboard").status_code == 200

    # 3. Auth signup endpoint
    test_email = f"testclient_{os.urandom(4).hex()}@example.com"
    signup_resp = client.post("/auth/signup", json={"name": "Test Client", "email": test_email, "password": "passclient123"})
    assert signup_resp.status_code == 200
    token = signup_resp.json()["token"]

    # 4. Auth me endpoint with token
    me_resp = client.get("/auth/me", headers={"Authorization": f"Bearer {token}"})
    assert me_resp.status_code == 200
    assert me_resp.json()["authenticated"] is True
    assert me_resp.json()["user"]["email"] == test_email

    # 5. Session current endpoint
    session_resp = client.get("/session/current", headers={"Authorization": f"Bearer {token}"})
    assert session_resp.status_code == 200

    # 6. Auth logout
    logout_resp = client.post("/auth/logout", headers={"Authorization": f"Bearer {token}"})
    assert logout_resp.status_code == 200

    print("  -> Passed: FastAPI routes, health, auth, and sessions verified successfully.")


def run_all():
    print("=" * 70)
    print("INTERVIEWIQ COMPLETE MULTI-LANGUAGE PLATFORM TEST SUITE")
    print("=" * 70)
    test_language_normalization()
    test_resume_extraction()
    test_runtime_support_inspection()
    test_python_code_execution()
    test_javascript_code_execution()
    test_compiler_limitation_handling()
    test_mcq_evaluation()
    test_interview_text_evaluation()
    test_auth_and_sessions()
    test_fastapi_app_routes()
    print("=" * 70)
    print("ALL TESTS PASSED SUCCESSFULLY! (10/10 TEST SUITES GREEN)")
    print("=" * 70)


if __name__ == "__main__":
    run_all()
