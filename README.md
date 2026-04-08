# Google Native Multi-Agent Life Ops System

FastAPI service that uses Google ADK with Vertex AI Gemini, BigQuery, and Google Calendar to manage tasks, notes, and scheduling through a single API.

## Architecture

- FastAPI exposes `/query`, `/tasks`, `/notes`, `/events`, and `/health`.
- A Google ADK root agent coordinates three specialist agents for tasks, calendar operations, and notes.
- BigQuery stores tasks and notes in the `life_ops` dataset.
- Google Calendar is the scheduling source of truth.
- Every external interaction is wrapped as an MCP-style tool with structured outputs and logging.

## Project Structure

```text
app/
  agent.py
  main.py
  config/
    settings.py
  tools/
    bq_tools.py
    calendar_tools.py
    common.py
tests/
requirements.txt
README.md
```

## Environment Variables

Set these before starting the API:

```bash
export GOOGLE_CLOUD_PROJECT="your-project-id"
export GOOGLE_GENAI_USE_VERTEXAI="TRUE"
export GOOGLE_CLOUD_LOCATION="us-central1"
export VERTEX_AI_LOCATION="us-central1"
export BIGQUERY_DATASET="life_ops"
export CALENDAR_ID="primary"
export SERVICE_TIMEZONE="Europe/Vilnius"
export LOG_LEVEL="INFO"
```

## Authentication

This project assumes Application Default Credentials only.

Local development:

```bash
gcloud auth application-default login
```

Cloud Run:

- Deploy with a service account that has BigQuery and Google Calendar access.
- Do not rely on local key files.

## BigQuery Setup

The app bootstraps the dataset and tables on startup when `BOOTSTRAP_BIGQUERY_ON_STARTUP=true`.

Tables:

- `tasks(id STRING, title STRING, deadline TIMESTAMP, created_at TIMESTAMP)`
- `notes(id STRING, content STRING, created_at TIMESTAMP)`

## Install And Run

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
uvicorn app.main:app --reload
```

## API Examples

Create or query through the agent:

```bash
curl -X POST http://127.0.0.1:8000/query \
  -H "Content-Type: application/json" \
  -d '{"message":"I have a meeting tomorrow at 3"}'
```

Get tasks:

```bash
curl http://127.0.0.1:8000/tasks
```

Get notes:

```bash
curl http://127.0.0.1:8000/notes
```

Get events:

```bash
curl http://127.0.0.1:8000/events
```

## Example Queries

- `I have a meeting tomorrow at 3`
- `Add task: study for exam Friday`
- `Store note: ask professor about grading rubric`
- `Plan my day`

## Cloud Run Readiness

- Stateless FastAPI service
- ADC-based auth
- Env-driven configuration
- No local persistence required

## Notes

- If a date or time is ambiguous, the agent should ask a follow-up question instead of guessing.
- The planner suggests time blocks but does not auto-create events unless explicitly asked.
- Package installation and live Google API calls require an internet-enabled environment.
