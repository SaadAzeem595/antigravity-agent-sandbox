# 🛠️ Core Tech Stack & Frameworks
The agents within this sandbox utilize variations of the following modern AI engineering stacks:

Orchestration: LangChain, LangGraph, CrewAI, Antigravity Core

Engines: Advanced Large Language Models (LLMs) & Custom Embeddings

APIs & Backends: FastAPI, Python 3.12+

Infrastructure & Tracking: MLflow, Docker, Virtual Environments (venv)

## ⚙️ Getting Started (Global Guide)
To explore, run, or build upon the agents in this sandbox, follow these foundational setup steps:

1. Clone the Repository
Bash
git clone [https://github.com/your-username/antigravity-agent-sandbox.git](https://github.com/your-username/antigravity-agent-sandbox.git)
cd antigravity-agent-sandbox
2. Environment Setup
Each agent typically runs inside its own subdirectory with a dedicated environment, but you can spin up a localized workspace easily:

PowerShell
### Navigate to a specific agent directory
cd weather-assistant

### Create a Python 3.12+ virtual environment
py -3.12 -m venv venv

### Activate the virtual environment
### On Windows (PowerShell):
.\venv\Scripts\Activate.ps1
### (Note: If you encounter an Execution Policy error, run: Set-ExecutionPolicy -Scope Process -ExecutionPolicy Bypass)

OPENAI_API_KEY=your_openai_key_here
ANTHROPIC_API_KEY=your_anthropic_key_here
# Agent-specific keys (e.g., OpenWeatherMap, Serper, etc.)
