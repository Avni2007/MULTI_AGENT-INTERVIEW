# InterviewIQ — Multi-Agent AI Interview & Assessment Platform

[![Azure Foundry](https://img.shields.io/badge/Azure-Foundry%20Agent%20Service-0078D4?logo=microsoftazure)](https://azure.microsoft.com/)
[![Agent Framework](https://img.shields.io/badge/Microsoft-Agent%20Framework-blue)](https://github.com/microsoft/agent-framework)
[![Python 3.10+](https://img.shields.io/badge/Python-3.10+-3776AB?logo=python)](https://python.org)
[![FastAPI](https://img.shields.io/badge/FastAPI-0.115+-009688?logo=fastapi)](https://fastapi.tiangolo.com)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)

**InterviewIQ** is an enterprise-grade AI technical assessment and mock interview preparation platform built on the **Microsoft Azure Foundry Agent Service**, **Microsoft Agent Framework**, and **Azure Document Intelligence**. It dynamically personalizes mock tests to each candidate's verified resume skills, supporting all modern programming languages with real-time compilation, test grading, and behavioral interview synthesis.

---

## Key Features

- **7 Microsoft Foundry Agents**: Collaborative multi-agent architecture utilizing the Agent-to-Agent (A2A) protocol and OpenAI `gpt-4.1-mini`.
- **Universal Multi-Language Compiler Engine**: Full execution and test case evaluation for all candidate languages (**Python**, **JavaScript**, **TypeScript**, **SQL**, **Java**, **C++**, **Go**, **Rust**, **C#**, **Kotlin**, **Swift**, **Ruby**, **PHP**).
- **Process-Isolated Sandboxing**: Strips all sensitive host environment credentials, enforces 6.0s execution timeouts, and truncates large outputs.
- **Dual Execution Workflows**:
  - `▶ Run Code`: Evaluates sample visible test cases or executes freeform custom stdin input in real time.
  - `✓ Submit Answer`: Runs all visible and hidden test cases, computes scoring (0–100), and invokes the Interview Feedback Agent.
- **5 Comprehensive Assessment Categories**:
  1. *Programming Language Coding*: Language-specific algorithms and problem solving.
  2. *Data Structures & Algorithms (DSA)*: LeetCode-style algorithmic challenges with starter code.
  3. *Core Computer Science*: Interactive MCQs covering OOP, DBMS, OS, Computer Networks, and System Design.
  4. *Aptitude & Logical Reasoning*: Quantitative, logical, and verbal problem solving.
  5. *Resume-Based Behavioral Interview*: Questions grounded directly in the candidate's actual projects and experience evaluated using the STAR method.
- **Resume Intelligence (PDF / DOCX)**: Ingestion via Azure Document Intelligence (`prebuilt-layout`) producing an 8-category scorecard (Structure, Skills, Experience, Projects, Achievements, Education, Job Alignment, Clarity).
- **Modern White & Blue UI**: Clean, high-contrast visual design, integrated code editor with Tab indentation support, draft code persistence, and developer console.
- **Candidate Authentication & History**: Secure PBKDF2 salted password hashing, session tokens, and chronological assessment dashboard.

---

## Multi-Agent Architecture

```
                  ┌─────────────────────────────────────────┐
                  │          Candidate Web Client           │
                  │   (White & Blue Interactive Studio)     │
                  └────────────────────┬────────────────────┘
                                       │ HTTP / REST
                                       ▼
                  ┌─────────────────────────────────────────┐
                  │        InterviewIQ Orchestrator         │
                  │   (FastAPI + Session & State Engine)    │
                  └─────┬──────────────┬──────────────┬─────┘
                        │              │              │
      ┌─────────────────┘              │              └─────────────────┐
      ▼                                ▼                                ▼
┌───────────────────────┐   ┌───────────────────────┐   ┌───────────────────────┐
│  Resume Intelligence  │   │ Adaptive Test Planner │   │  Question Forge Agent │
│         Agent         │   │         Agent         │   │                       │
│ (Azure Doc Intelligence)   │ (Language & Skill Fit)│   │ (Grounded Generation) │
└───────────────────────┘   └───────────────────────┘   └───────────────────────┘
      │                                │                                │
      └────────────────────────────────┼────────────────────────────────┘
                                       │ A2A Protocol
      ┌────────────────────────────────┼────────────────────────────────┐
      ▼                                ▼                                ▼
┌───────────────────────┐   ┌───────────────────────┐   ┌───────────────────────┐
│ Code Evaluation Agent │   │   Interview Feedback  │   │  Performance Insights │
│                       │   │         Agent         │   │         Agent         │
│  (Multi-Lang Sandbox) │   │  (Scoring & Criteria) │   │  (Readiness & Verdict)│
└───────────────────────┘   └───────────────────────┘   └───────────────────────┘
```

---

## Directory Structure

```
├── azure.yaml                                        # Azure Developer CLI (azd) deployment manifest
├── AGENTS.md                                         # Microsoft Foundry hosted agent instructions
├── README.md                                         # Platform documentation
├── .gitignore                                        # Secret & build artifact exclusions
└── src/
    └── agent-framework-agent-basic-responses/
        ├── index.html                                # Modern White & Blue frontend interface
        ├── webapp.py                                 # FastAPI application & API endpoints
        ├── assessment.py                             # Multi-language compiler engine & test evaluation
        ├── agents.py                                 # 7 Microsoft Foundry agents & Azure AI client
        ├── a2a_assessment.py                         # Agent-to-Agent (A2A) protocol implementation
        ├── auth.py                                   # Candidate authentication & SQLite session store
        ├── main.py                                   # Microsoft Foundry Hosted Agent entrypoint
        ├── requirements.txt                          # Python dependencies
        ├── Dockerfile                                # Container image definition
        ├── .env.example                              # Environment variable configuration template
        ├── test_compiler_sandbox.py                  # Sandboxed execution unit tests (13/13 passing)
        ├── verify_compiler_endpoints.py              # Live API compiler verification (11/11 passing)
        ├── test_interviewiq.py                       # Comprehensive test suite (10/10 passing)
        └── verify_all_workflows.py                   # End-to-end multi-workflow verification
```

---

## Getting Started

### 1. Prerequisites
- Python 3.10+
- Node.js v20+ (for JavaScript and native TypeScript execution)
- Git

### 2. Clone the Repository
```bash
git clone https://github.com/Avni2007/MULTI_AGENT-INTERVIEW.git
cd MULTI_AGENT-INTERVIEW
```

### 3. Set Up Environment Variables
Copy `.env.example` in the service directory to `.env` and fill in your Azure Foundry and Document Intelligence credentials:
```bash
cp src/agent-framework-agent-basic-responses/.env.example src/agent-framework-agent-basic-responses/.env
```

Edit `src/agent-framework-agent-basic-responses/.env`:
```ini
FOUNDRY_PROJECT_ENDPOINT=https://<your-project>.services.ai.azure.com/api/projects/<project-name>
AZURE_DOCUMENT_INTELLIGENCE_ENDPOINT=https://<your-doc-intelligence>.cognitiveservices.azure.com/
AZURE_DOCUMENT_INTELLIGENCE_KEY=your_document_intelligence_key_here

AZURE_AI_MODEL_DEPLOYMENT_NAME=gpt-4.1-mini

AZURE_TENANT_ID=your_azure_tenant_id_here
AZURE_CLIENT_ID=your_azure_client_id_here
AZURE_CLIENT_SECRET=your_azure_client_secret_here
```

### 4. Install Dependencies
```bash
cd src/agent-framework-agent-basic-responses
python -m venv .venv
# Windows:
.venv\Scripts\activate
# Linux/macOS:
source .venv/bin/activate

pip install -r requirements.txt
```

### 5. Run the Application Locally
```bash
python -m uvicorn webapp:app --host 127.0.0.1 --port 8000
```
Open **`http://127.0.0.1:8000`** in your browser.

---

## Running Verification Tests

Run the full automated test suite:
```bash
# Platform & Agent integration tests
python test_interviewiq.py

# Compiler sandboxing, security & timeout tests
python test_compiler_sandbox.py

# Live API endpoint tests (with web server running on port 8000)
python verify_compiler_endpoints.py

# Complete 11-step end-to-end workflow verification
python verify_all_workflows.py
```

---

## Deployment to Microsoft Azure Foundry

Deploy using the **Azure Developer CLI (`azd`)**:
```bash
# Log in to Azure
azd auth login

# Provision and deploy resources
azd up
```

---

## License

This project is licensed under the MIT License - see the LICENSE file for details.
