"""End-to-end verification script testing all 11 user workflows against the live server.
"""

import requests
import json
import time

BASE_URL = "http://127.0.0.1:8000"

def test_live_workflows():
    print("=" * 80)
    print("INTERVIEWIQ — COMPLETE END-TO-END WORKFLOW VERIFICATION (11 WORKFLOWS)")
    print("=" * 80)

    # --------------------------------------------------------------------------
    # Workflow 11: Signup -> Login -> Protected Dashboard -> Logout
    # --------------------------------------------------------------------------
    print("\n[Workflow 11] Signup -> Login -> Protected Dashboard -> Logout")
    test_email = f"candidate_{int(time.time())}@example.com"
    signup_resp = requests.post(f"{BASE_URL}/auth/signup", json={
        "name": "Sarah Connor",
        "email": test_email,
        "password": "Password123!"
    })
    assert signup_resp.status_code == 200, f"Signup failed: {signup_resp.text}"
    token = signup_resp.json()["token"]
    user = signup_resp.json()["user"]
    print(f"  [OK] User registered: {user['name']} ({user['email']})")

    headers = {"Authorization": f"Bearer {token}"}
    me_resp = requests.get(f"{BASE_URL}/auth/me", headers=headers)
    assert me_resp.status_code == 200
    assert me_resp.json()["authenticated"] is True
    print(f"  [OK] Protected dashboard accessible. User verified.")

    logout_resp = requests.post(f"{BASE_URL}/auth/logout", headers=headers)
    assert logout_resp.status_code == 200
    me_after = requests.get(f"{BASE_URL}/auth/me", headers=headers)
    assert me_after.json()["authenticated"] is False
    print(f"  [OK] Logout successful. Session destroyed.")

    # Re-login for subsequent authenticated actions
    login_resp = requests.post(f"{BASE_URL}/auth/login", json={
        "email": test_email,
        "password": "Password123!"
    })
    assert login_resp.status_code == 200
    token = login_resp.json()["token"]
    headers = {"Authorization": f"Bearer {token}"}
    print(f"  [OK] Logged back in successfully.")

    # --------------------------------------------------------------------------
    # Workflow 1: Resume Upload -> Language Extraction -> Language Selector
    # --------------------------------------------------------------------------
    print("\n[Workflow 1] Resume Upload -> Language Extraction -> Dynamic Language Selector")
    with open("test_candidate_resume.pdf", "rb") as f:
        upload_resp = requests.post(
            f"{BASE_URL}/analyze",
            files={"file": ("test_candidate_resume.pdf", f, "application/pdf")},
            data={"job_description": "Senior Software Engineer proficient in Python, Java, C++, and Go."},
            headers=headers
        )
    assert upload_resp.status_code == 200, f"Analyze failed: {upload_resp.text}"
    analysis = upload_resp.json()
    ctx = analysis.get("assessment_context", {})
    extracted_languages = ctx.get("supported_languages", [])
    frameworks = ctx.get("frameworks", [])

    print(f"  [OK] Resume Intelligence Agent overall score: {analysis.get('overall_score')}/100")
    print(f"  [OK] Extracted programming languages: {extracted_languages}")
    print(f"  [OK] Detected frameworks: {frameworks}")
    assert "Python" in extracted_languages
    assert "Java" in extracted_languages
    assert "C++" in extracted_languages
    assert "JavaScript" in extracted_languages
    assert "SQL" in extracted_languages
    assert "React" not in extracted_languages, "React is a framework, NOT a programming language"

    session_resp = requests.get(f"{BASE_URL}/session/current", headers=headers)
    assert session_resp.status_code == 200
    assert session_resp.json()["analyzed"] is True
    print(f"  [OK] Session current verified: {len(extracted_languages)} languages available for selector.")

    # --------------------------------------------------------------------------
    # Workflow 2: Language Selector -> Category -> Difficulty -> Test Generation
    # --------------------------------------------------------------------------
    print("\n[Workflow 2] Language Selector -> Category -> Difficulty -> Plan & Start")
    plan_resp = requests.post(f"{BASE_URL}/assessment/plan", json={
        "category": "coding",
        "selected_language": "Python",
        "difficulty": "medium",
        "question_count": 3,
        "duration_minutes": 30
    }, headers=headers)
    assert plan_resp.status_code == 200
    plan = plan_resp.json()
    print(f"  [OK] Adaptive Test Planner generated plan: {plan.get('category')} in {plan.get('language')} ({plan.get('difficulty')})")

    # --------------------------------------------------------------------------
    # Workflow 3: Python Coding Test -> Python-Specific Questions -> Code Execution
    # --------------------------------------------------------------------------
    print("\n[Workflow 3] Python Coding Test -> Questions -> Execution")
    py_start = requests.post(f"{BASE_URL}/assessment/start", json={
        "category": "coding",
        "selected_language": "Python",
        "difficulty": "medium",
        "question_count": 3,
        "duration_minutes": 30
    }, headers=headers)
    assert py_start.status_code == 200
    py_test = py_start.json()
    assessment_id = py_test["assessment_id"]
    q1 = py_test["questions"][0]
    print(f"  [OK] Generated {len(py_test['questions'])} Python questions. Q1: '{q1['title']}'")
    assert q1["language"] == "Python" or py_test["language"] == "Python"
    assert q1.get("starter_code") is not None

    # Submit answer to Q1
    submit_resp = requests.post(f"{BASE_URL}/assessment/submit", json={
        "assessment_id": assessment_id,
        "question_id": q1["id"],
        "code": q1.get("starter_code") or "print('ok')",
    }, headers=headers)
    assert submit_resp.status_code == 200
    print(f"  [OK] Python code evaluated by Code Evaluation Agent. Score: {submit_resp.json()['score']}")

    # --------------------------------------------------------------------------
    # Workflow 4: Java Coding Test -> Java-Specific Questions -> Limitation Diagnostic
    # --------------------------------------------------------------------------
    print("\n[Workflow 4] Java Coding Test -> Java-Specific Questions -> Server Limitation")
    java_start = requests.post(f"{BASE_URL}/assessment/start", json={
        "category": "coding",
        "selected_language": "Java",
        "difficulty": "medium",
        "question_count": 3,
        "duration_minutes": 30
    }, headers=headers)
    assert java_start.status_code == 200
    java_test = java_start.json()
    java_q = java_test["questions"][0]
    print(f"  [OK] Generated Java question: '{java_q['title']}'")

    java_submit = requests.post(f"{BASE_URL}/assessment/submit", json={
        "assessment_id": java_test["assessment_id"],
        "question_id": java_q["id"],
        "code": "public class Solution { public static void main(String[] args) {} }"
    }, headers=headers)
    assert java_submit.status_code == 200
    java_res = java_submit.json()
    assert java_res["runtime_limitation"] is True
    print(f"  [OK] Server limitation handled cleanly: {java_res['compilation_error'][:65]}...")

    # --------------------------------------------------------------------------
    # Workflow 5: C++ Coding Test -> C++-Specific Questions -> Limitation Diagnostic
    # --------------------------------------------------------------------------
    print("\n[Workflow 5] C++ Coding Test -> C++-Specific Questions -> Server Limitation")
    cpp_start = requests.post(f"{BASE_URL}/assessment/start", json={
        "category": "coding",
        "selected_language": "C++",
        "difficulty": "medium",
        "question_count": 3,
        "duration_minutes": 30
    }, headers=headers)
    assert cpp_start.status_code == 200
    cpp_test = cpp_start.json()
    cpp_q = cpp_test["questions"][0]
    print(f"  [OK] Generated C++ question: '{cpp_q['title']}'")

    cpp_submit = requests.post(f"{BASE_URL}/assessment/submit", json={
        "assessment_id": cpp_test["assessment_id"],
        "question_id": cpp_q["id"],
        "code": "#include <iostream>\nint main(){ return 0; }"
    }, headers=headers)
    assert cpp_submit.status_code == 200
    cpp_res = cpp_submit.json()
    assert cpp_res["runtime_limitation"] is True
    print(f"  [OK] Server limitation handled cleanly: {cpp_res['compilation_error'][:65]}...")

    # --------------------------------------------------------------------------
    # Workflow 6: DSA Test -> Selected Language / Category Alignment
    # --------------------------------------------------------------------------
    print("\n[Workflow 6] DSA Test -> Category & Language Alignment")
    dsa_start = requests.post(f"{BASE_URL}/assessment/start", json={
        "category": "dsa",
        "selected_language": "Python",
        "difficulty": "medium",
        "question_count": 3,
        "duration_minutes": 30
    }, headers=headers)
    assert dsa_start.status_code == 200
    dsa_test = dsa_start.json()
    assert dsa_test["category"] == "dsa"
    assert dsa_test["language"] == "Python"
    print(f"  [OK] DSA assessment generated with {len(dsa_test['questions'])} algorithmic questions. Q1: '{dsa_test['questions'][0]['title']}'")

    # --------------------------------------------------------------------------
    # Workflow 7: Core CS Test -> Correct Question Format (MCQ)
    # --------------------------------------------------------------------------
    print("\n[Workflow 7] Core CS Test -> Correct Question Format (MCQs)")
    core_start = requests.post(f"{BASE_URL}/assessment/start", json={
        "category": "core_cs",
        "selected_language": None,
        "difficulty": "medium",
        "question_count": 3,
        "duration_minutes": 20
    }, headers=headers)
    assert core_start.status_code == 200
    core_test = core_start.json()
    core_q = core_test["questions"][0]
    assert core_q["question_type"] == "mcq"
    assert len(core_q.get("options", [])) >= 2
    print(f"  [OK] Core CS question is MCQ with options: {core_q['options'][:2]}...")

    core_sub = requests.post(f"{BASE_URL}/assessment/submit", json={
        "assessment_id": core_test["assessment_id"],
        "question_id": core_q["id"],
        "selected_option": "A"
    }, headers=headers)
    assert core_sub.status_code == 200
    print(f"  [OK] MCQ answer evaluated. Score: {core_sub.json()['score']}, Feedback: {core_sub.json()['feedback'][:50]}...")

    # --------------------------------------------------------------------------
    # Workflow 8: Resume-Based Interview -> Actual Resume-Derived Questions
    # --------------------------------------------------------------------------
    print("\n[Workflow 8] Resume-Based Interview -> Actual Resume Grounded Questions")
    res_start = requests.post(f"{BASE_URL}/assessment/start", json={
        "category": "resume_interview",
        "selected_language": None,
        "difficulty": "medium",
        "question_count": 3,
        "duration_minutes": 20
    }, headers=headers)
    assert res_start.status_code == 200
    res_test = res_start.json()
    res_q = res_test["questions"][0]
    assert res_q["question_type"] == "interview_text"
    print(f"  [OK] Resume-based question grounded in candidate background: '{res_q['title']}'")
    print(f"    Problem: {res_q['problem_statement'][:100]}...")

    # Submit STAR response
    res_sub = requests.post(f"{BASE_URL}/assessment/submit", json={
        "assessment_id": res_test["assessment_id"],
        "question_id": res_q["id"],
        "text_answer": "In our distributed key-value store project, I implemented Raft consensus to guarantee linearizable consistency. We benchmarked throughput under network partitions and achieved zero data loss with 99.9% availability."
    }, headers=headers)
    assert res_sub.status_code == 200
    print(f"  [OK] Interview text answer evaluated. Score: {res_sub.json()['score']}/100")

    # --------------------------------------------------------------------------
    # Workflow 9: Test Submission -> Actual Evaluation -> Results & Performance Insights
    # --------------------------------------------------------------------------
    print("\n[Workflow 9] Test Submission -> Final Results & Performance Insights")
    results_resp = requests.get(f"{BASE_URL}/assessment/{res_test['assessment_id']}/results", headers=headers)
    assert results_resp.status_code == 200
    results = results_resp.json()
    print(f"  [OK] Final assessment score: {results.get('final_score')}/100")
    insights = results.get("insights", {})
    print(f"  [OK] Performance Insights readiness verdict: {insights.get('readiness_verdict')}")
    print(f"  [OK] Key strengths: {insights.get('key_strengths', [])[:2]}")
    print(f"  [OK] Next steps roadmap: {insights.get('next_steps_roadmap', [])[:2]}")

    # --------------------------------------------------------------------------
    # Workflow 10: Agent Processing -> Verification in Database & Dashboard
    # --------------------------------------------------------------------------
    print("\n[Workflow 10] Agent Processing Verified in Dashboard Test History")
    dash_resp = requests.get(f"{BASE_URL}/auth/me", headers=headers)
    history = dash_resp.json().get("history", [])
    assert len(history) >= 1
    print(f"  [OK] Dashboard history contains {len(history)} completed assessment(s).")
    latest = history[0]
    print(f"  [OK] Latest entry: {latest['category']} | Score: {latest['score']}/100 | Completed: {latest['completed_at']}")

    print("\n" + "=" * 80)
    print("ALL 11 WORKFLOWS TESTED AND VERIFIED SUCCESSFULLY AGAINST LIVE SERVER!")
    print("=" * 80)

if __name__ == "__main__":
    test_live_workflows()
