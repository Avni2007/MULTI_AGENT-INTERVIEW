"""Comprehensive test suite for InterviewIQ Code Compiler Sandbox.
Tests Python, JavaScript, SQL, C++, Java, timeout, custom input, syntax errors,
runtime errors, and environment credential isolation.
"""

import sys
import assessment

def run_tests():
    print("=== Testing InterviewIQ Code Compiler Sandbox ===")

    # 1. Simple valid Python
    res1 = assessment.run_code_sandbox("Python", 'print("Hello InterviewIQ")')
    assert res1.status == "success", f"res1 status: {res1.status}"
    assert "Hello InterviewIQ" in res1.stdout, f"res1 stdout: {res1.stdout}"
    print("[PASS] 1. Python simple valid code: " + res1.stdout.strip())

    # 2. Syntax error
    res2 = assessment.run_code_sandbox("Python", "def foo(")
    assert res2.status == "syntax_error", f"res2 status: {res2.status}"
    assert res2.compilation_error, "res2 should have compilation_error"
    print("[PASS] 2. Python syntax error caught successfully.")

    # 3. Runtime error
    res3 = assessment.run_code_sandbox("Python", "print(1 / 0)", custom_input="")
    assert res3.status == "runtime_error", f"res3 status: {res3.status}"
    assert "ZeroDivisionError" in res3.stderr, f"res3 stderr: {res3.stderr}"
    print("[PASS] 3. Python runtime error caught: ZeroDivisionError.")

    # 4. Correct output with Custom stdin
    res4 = assessment.run_code_sandbox("Python", 's = input()\nprint(f"Recv: {s}")', custom_input="AlphaBeta")
    assert res4.status == "success", f"res4 status: {res4.status}"
    assert "Recv: AlphaBeta" in res4.stdout, f"res4 stdout: {res4.stdout}"
    print("[PASS] 4. Python custom stdin input: " + res4.stdout.strip())

    # 5. Timeout behavior
    res5 = assessment.run_code_sandbox("Python", "import time\ntime.sleep(15)", custom_input="")
    assert res5.status == "timeout", f"res5 status: {res5.status}"
    print("[PASS] 5. Python timeout caught cleanly within wall-clock limit.")

    # 6. Environment isolation (credential leakage protection)
    code_leak_check = """
import os
forbidden = ['AZURE_CLIENT_SECRET', 'AZURE_DOCUMENT_INTELLIGENCE_KEY', 'FOUNDRY_PROJECT_ENDPOINT']
found = [k for k in forbidden if k in os.environ]
if found:
    print('LEAKED:' + ','.join(found))
else:
    print('ISOLATED_OK')
"""
    res6 = assessment.run_code_sandbox("Python", code_leak_check, custom_input="")
    assert res6.status == "success"
    assert "ISOLATED_OK" in res6.stdout, f"Credential leaked in environment: {res6.stdout}"
    print("[PASS] 6. Environment credential isolation verified (0 secrets accessible to user code).")

    # 7. JavaScript valid program
    res7 = assessment.run_code_sandbox("JavaScript", 'console.log("Hello InterviewIQ JS");')
    assert res7.status == "success", f"res7 status: {res7.status}"
    assert "Hello InterviewIQ JS" in res7.stdout, f"res7 stdout: {res7.stdout}"
    print("[PASS] 7. JavaScript valid program: " + res7.stdout.strip())

    # 8. JavaScript runtime error
    res8 = assessment.run_code_sandbox("JavaScript", 'throw new Error("JS Crash Test");', custom_input="")
    assert res8.status == "runtime_error", f"res8 status: {res8.status}"
    assert "JS Crash Test" in res8.stderr, f"res8 stderr: {res8.stderr}"
    print("[PASS] 8. JavaScript runtime error caught.")

    # 9. SQL in-memory query execution
    res9 = assessment.run_code_sandbox("SQL", "SELECT name, department, salary FROM employees WHERE salary >= 95000;")
    assert res9.status == "success", f"res9 status: {res9.status}"
    assert "Alice" in res9.stdout and "Evan" in res9.stdout
    print("[PASS] 9. SQL in-memory execution formatted table:\n" + res9.stdout)

    # 10. C++ Execution & Syntax Analysis (Multi-Language Engine)
    res10 = assessment.run_code_sandbox("C++", '#include <iostream>\nint main() {\n    std::cout << "Hello InterviewIQ C++" << std::endl;\n    return 0;\n}')
    assert res10.status == "success", f"res10 status: {res10.status}, stderr: {res10.stderr}"
    assert "Hello InterviewIQ C++" in res10.stdout, f"res10 stdout: {res10.stdout}"
    print("[PASS] 10. C++ execution verified in Multi-Language Engine: " + res10.stdout.strip())

    # 11. Java Execution & Syntax Analysis (Multi-Language Engine)
    res11 = assessment.run_code_sandbox("Java", 'public class Solution {\n    public static void main(String[] args) {\n        System.out.println("Hello InterviewIQ Java");\n    }\n}')
    assert res11.status == "success", f"res11 status: {res11.status}, stderr: {res11.stderr}"
    assert "Hello InterviewIQ Java" in res11.stdout, f"res11 stdout: {res11.stdout}"
    print("[PASS] 11. Java execution verified in Multi-Language Engine: " + res11.stdout.strip())

    # 12. Submit Code question grading with test cases
    sample_q = assessment.AssessmentQuestion(
        id="q_test_1",
        category="coding",
        question_type="coding",
        language="Python",
        topic="Math",
        title="Sum of Two Numbers",
        difficulty="easy",
        problem_statement="Read two integers on one line and print their sum.",
        input_description="Two space-separated integers",
        output_description="Their sum",
        starter_code="import sys\n# write code\n",
        visible_tests=[
            assessment.TestCase(input="3 5\n", expected_output="8\n"),
            assessment.TestCase(input="10 20\n", expected_output="30\n"),
        ],
        hidden_tests=[
            assessment.TestCase(input="100 200\n", expected_output="300\n"),
        ],
    )

    # 12a. Correct submission -> 100% score
    correct_solution = "import sys\nnums = [int(x) for x in sys.stdin.read().split()]\nprint(sum(nums))\n"
    res12a = assessment.execute_question("Python", sample_q, code=correct_solution)
    assert res12a.score == 100, f"Expected 100, got {res12a.score}"
    assert res12a.passed_tests == 3, f"Expected 3 passes, got {res12a.passed_tests}"
    print(f"[PASS] 12a. Submit Code 100% correct evaluation ({res12a.passed_tests}/{res12a.total_tests} passed).")

    # 12b. Incorrect submission -> partial/0% score
    wrong_solution = "import sys\nprint(42)\n"
    res12b = assessment.execute_question("Python", sample_q, code=wrong_solution)
    assert res12b.score == 0, f"Expected 0, got {res12b.score}"
    assert res12b.passed_tests == 0
    print(f"[PASS] 12b. Submit Code incorrect evaluation ({res12b.passed_tests}/{res12b.total_tests} passed).")

    # 12c. Run Code with sample test cases (no custom input) -> does not grade final question
    res12c = assessment.run_code_sandbox("Python", correct_solution, question=sample_q)
    assert res12c.status == "success"
    assert len(res12c.test_results) == 2, f"Expected 2 visible test results, got {len(res12c.test_results)}"
    assert all(tr.passed for tr in res12c.test_results)
    print(f"[PASS] 12c. Run Code sample test cases verified (2/2 visible tests passed).")

    print("\nALL 13 COMPILER SANDBOX TESTS PASSED SUCCESSFULLY! [OK]")

if __name__ == "__main__":
    run_tests()
