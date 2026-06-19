# 🌌 Antigravity Agent Sandbox

Welcome to the **Antigravity Agent Sandbox**! This repository is a unified workspace for developing, evaluating, and testing autonomous AI agents.

## 📁 Repository Structure

The sandbox is organized into specialized agent subdirectories:

1. **[ambient-expense-agent](file:///D:/Vibecode_an_ADK_2.0/ambient-expense-agent/ambient-expense-agent)**: An expense auditing ReAct agent with local test suites and automated evaluation loops (including PII leak and prompt injection scans).
2. **[customer-support-agent](file:///D:/Vibecode_an_ADK_2.0/ambient-expense-agent/customer-support-agent)**: A support agent designed to handle user requests and customer service queries.

---

## 🛠️ Core Tech Stack & Frameworks

The agents within this sandbox utilize variations of the following modern AI engineering stacks:
- **Orchestration**: LangChain, LangGraph, CrewAI, Antigravity Core / ADK
- **Engines**: Advanced Large Language Models (LLMs) & Custom Embeddings
- **APIs & Backends**: FastAPI, Python 3.12+
- **Infrastructure & Tracking**: MLflow, Docker, Virtual Environments (venv)

---

## ⚙️ Getting Started (Global Guide)

To explore, run, or build upon the agents in this sandbox, follow these foundational setup steps:

### 1. Clone the Repository
```bash
git clone https://github.com/SaadAzeem595/antigravity-agent-sandbox.git
cd antigravity-agent-sandbox
```

### 2. Run an Agent Project
Each agent runs inside its own subdirectory with its own dependencies. For example, to set up and run the **Ambient Expense Agent**:

```bash
# Navigate to the agent directory
cd ambient-expense-agent

# Install dependencies using agents-cli/uv
agents-cli install

# Start the local development playground
agents-cli playground
```
