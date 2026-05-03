# Calendar Planning Agent

A Calendar Augmentation Agent that takes a user's natural-language goal,
decomposes it into subtasks via an LLM, finds free time in their Google
Calendar, schedules those subtasks across available slots, and asks for
approval before writing anything to the calendar.

## Current Status

The current integration branch has the core mock-mode application flow implemented:
configurable LLM client wrappers, calendar wrappers, free-slot computation,
mock calendar, validator, heuristics, graph nodes, Streamlit UI, approval
controls, and app session flow. `.venv/bin/pytest -q` currently reports
`58 passed`.

Remaining validation work includes a full `CALENDAR_MODE=mock` Streamlit
walkthrough reject-path check and live Google Calendar verification. A
Vertex AI approve-path smoke test with mock calendar has been verified.

## Architecture

| Module | Location | Purpose |
|---|---|---|
| **Frontend** | `src/frontend/` | Streamlit UI — intake form, schedule display, approve/reject |
| **Calendar API** | `src/calendar_api/` | Google Calendar OAuth, event fetch/create, free-slot computation |
| **Orchestration** | `src/orchestration/` | LangGraph directed graph — decompose → schedule → validate → approve → write |
| **Validator** | `src/validator/` | Pure-Python deterministic constraint checker (no LLM) |
| **LLM Client** | `src/llm_client/` | Configurable Anthropic/Gemini/Vertex AI/OpenAI-compatible/mock wrapper with retry logic |

## Quick Start

```bash
# 1. Clone and enter the project
cd calendar_planning_agent

# 2. Create a virtual environment
python -m venv .venv && source .venv/bin/activate

# 3. Install dependencies
pip install -r requirements.txt

# 4. Copy env template and fill in keys
cp .env.example .env

# 5. Run fully locally with mock calendar + mock LLM
CALENDAR_MODE=mock LLM_PROVIDER=mock streamlit run src/app.py

# 6. Run tests
.venv/bin/pytest -q
```

## Production Deployment (AWS)

See `infrastructure/` for CloudFormation templates and deploy scripts.
The application is containerised via `Dockerfile` and can be deployed to
AWS ECS / Fargate behind an ALB, with secrets stored in AWS Secrets Manager.
