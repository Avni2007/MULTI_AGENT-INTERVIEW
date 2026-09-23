@echo off
setlocal
echo Starting Employability AI on http://localhost:8080 ...
"%~dp0.venv\Scripts\python.exe" "%~dp0src\agent-framework-agent-basic-responses\webapp.py"
pause
