"""End-to-end live API verification for InterviewIQ Compiler & Execution Sandboxing."""

import json
import urllib.request
import urllib.error

BASE_URL = "http://127.0.0.1:8000"

def post(endpoint, data):
    req = urllib.request.Request(
        f"{BASE_URL}{endpoint}",
        data=json.dumps(data).encode("utf-8"),
        headers={"Content-Type": "application/json"},
    )
    with urllib.request.urlopen(req, timeout=15) as resp:
        return json.loads(resp.read().decode("utf-8"))

def get(endpoint):
    req = urllib.request.Request(f"{BASE_URL}{endpoint}")
    with urllib.request.urlopen(req, timeout=15) as resp:
        return json.loads(resp.read().decode("utf-8"))

def run_tests():
    print("=== InterviewIQ Live API Compiler End-to-End Verification ===")

    # 1. GET /compiler/languages
    print("\n--- Test 1: GET /compiler/languages ---")
    langs_resp = get("/compiler/languages")
    languages = langs_resp.get("languages", [])
    assert len(languages) >= 5, "Expected at least 5 languages"
    supported_langs = [l["language"] for l in languages if l["supported"]]
    print(f"[PASS] Retrieved {len(languages)} languages. Executable runtimes: {supported_langs}")
    assert "Python" in supported_langs, "Python should be supported"
    assert "JavaScript" in supported_langs, "JavaScript should be supported"
    assert "SQL" in supported_langs, "SQL should be supported"

    # 2. POST /assessment/run - Python simple valid code
    print("\n--- Test 2: Python simple execution ---")
    res_py = post("/assessment/run", {
        "language": "Python",
        "code": 'print("Hello InterviewIQ Live")',
    })
    print("Status:", res_py.get("status"))
    print("Stdout:", res_py.get("stdout", "").strip())
    assert res_py["status"] == "success"
    assert "Hello InterviewIQ Live" in res_py["stdout"]
    print("[PASS] Python executed and returned stdout successfully.")

    # 3. POST /assessment/run - Python Syntax Error
    print("\n--- Test 3: Python syntax error ---")
    res_syn = post("/assessment/run", {
        "language": "Python",
        "code": "def broken_code(",
    })
    print("Status:", res_syn.get("status"))
    print("Stderr:", res_syn.get("stderr", "").strip()[:80])
    assert res_syn["status"] == "syntax_error"
    assert res_syn.get("compilation_error")
    print("[PASS] Python syntax error caught and classified correctly.")

    # 4. POST /assessment/run - Python Runtime Error
    print("\n--- Test 4: Python runtime error ---")
    res_rt = post("/assessment/run", {
        "language": "Python",
        "code": "val = 10 / 0",
        "custom_input": "",
    })
    print("Status:", res_rt.get("status"))
    print("Stderr:", res_rt.get("stderr", "").strip()[-60:])
    assert res_rt["status"] == "runtime_error"
    assert "ZeroDivisionError" in res_rt.get("stderr", "")
    print("[PASS] Python runtime error reported accurately.")

    # 5. POST /assessment/run - Python Custom Stdin Input
    print("\n--- Test 5: Python custom stdin input ---")
    res_stdin = post("/assessment/run", {
        "language": "Python",
        "code": "name = input()\nprint(f'Candidate: {name}')",
        "custom_input": "Sarah Connor",
    })
    print("Stdout:", res_stdin.get("stdout", "").strip())
    assert res_stdin["status"] == "success"
    assert "Candidate: Sarah Connor" in res_stdin["stdout"]
    print("[PASS] Custom stdin input piped and executed successfully.")

    # 6. POST /assessment/run - Python Timeout
    print("\n--- Test 6: Python timeout ---")
    res_to = post("/assessment/run", {
        "language": "Python",
        "code": "import time\ntime.sleep(20)",
        "custom_input": "",
    })
    print("Status:", res_to.get("status"))
    assert res_to["status"] == "timeout"
    print("[PASS] Timeout caught and handled within limit.")

    # 7. POST /assessment/run - JavaScript valid code
    print("\n--- Test 7: JavaScript execution ---")
    res_js = post("/assessment/run", {
        "language": "JavaScript",
        "code": 'console.log("Hello InterviewIQ JS Live");',
    })
    print("Stdout:", res_js.get("stdout", "").strip())
    assert res_js["status"] == "success"
    assert "Hello InterviewIQ JS Live" in res_js["stdout"]
    print("[PASS] JavaScript Node.js execution verified.")

    # 8. POST /assessment/run - SQL In-memory query
    print("\n--- Test 8: SQL query execution ---")
    res_sql = post("/assessment/run", {
        "language": "SQL",
        "code": "SELECT name, department, salary FROM employees WHERE salary > 90000;",
    })
    print("Output table:\n" + res_sql.get("stdout", "").strip())
    assert res_sql["status"] == "success"
    assert "Alice" in res_sql["stdout"]
    print("[PASS] SQL execution formatted table verified.")

    # 9. POST /assessment/run - C++ Multi-Language Engine Execution
    print("\n--- Test 9: C++ live engine execution ---")
    res_cpp = post("/assessment/run", {
        "language": "C++",
        "code": '#include <iostream>\nint main() {\n    std::cout << "Hello C++ Live" << std::endl;\n    return 0;\n}',
    })
    print("Status:", res_cpp.get("status"))
    print("Stdout:", res_cpp.get("stdout", "").strip())
    assert res_cpp["status"] == "success"
    assert "Hello C++ Live" in res_cpp["stdout"]
    print("[PASS] C++ executed live via Multi-Language Compiler Engine.")

    # 10. POST /assessment/run - Java Multi-Language Engine Execution
    print("\n--- Test 10: Java live engine execution ---")
    res_java = post("/assessment/run", {
        "language": "Java",
        "code": 'public class Solution {\n    public static void main(String[] args) {\n        System.out.println("Hello Java Live");\n    }\n}',
    })
    print("Status:", res_java.get("status"))
    print("Stdout:", res_java.get("stdout", "").strip())
    assert res_java["status"] == "success"
    assert "Hello Java Live" in res_java["stdout"]
    print("[PASS] Java executed live via Multi-Language Compiler Engine.")

    # 11. POST /assessment/run - TypeScript Native Node Execution
    print("\n--- Test 11: TypeScript native execution ---")
    res_ts = post("/assessment/run", {
        "language": "TypeScript",
        "code": 'const greeting: string = "Hello TypeScript Live";\nconsole.log(greeting);',
    })
    print("Status:", res_ts.get("status"))
    print("Stdout:", res_ts.get("stdout", "").strip())
    assert res_ts["status"] == "success"
    assert "Hello TypeScript Live" in res_ts["stdout"]
    print("[PASS] TypeScript executed live via native Node.js runtime.")

    print("\n=======================================================")
    print("ALL 10 LIVE COMPILER ENDPOINTS VERIFIED & GREEN! [OK]")
    print("=======================================================")

if __name__ == "__main__":
    run_tests()
