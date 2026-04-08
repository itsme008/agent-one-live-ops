from __future__ import annotations

import logging
from contextlib import asynccontextmanager
from typing import Any
from uuid import uuid4

from fastapi import FastAPI, HTTPException, Request
from pydantic import BaseModel, Field
from starlette.responses import HTMLResponse

from app.agent import get_agent_service
from app.config.settings import configure_logging, get_settings, log_structured
from app.tools.bq_tools import bootstrap_bigquery, get_notes_bq, get_tasks_bq
from app.tools.calendar_tools import get_calendar_events
from app.tools.common import ToolExecutionError

logger = logging.getLogger(__name__)


class QueryRequest(BaseModel):
    message: str = Field(min_length=1)
    user_id: str | None = None
    session_id: str | None = None


class QueryResponse(BaseModel):
    response: str
    tool_calls: list[dict[str, Any]]
    session_id: str


@asynccontextmanager
async def lifespan(_: FastAPI):
    configure_logging()
    settings = get_settings()
    log_structured(
        logger,
        logging.INFO,
        "startup",
        app_name=settings.app_name,
        project=settings.google_cloud_project,
        dataset=settings.bigquery_dataset,
        calendar_id=settings.calendar_id,
    )
    if settings.bootstrap_bigquery_on_startup:
        try:
            bootstrap_bigquery()
        except Exception as exc:
            log_structured(logger, logging.ERROR, "startup_bigquery_bootstrap_failed", error=str(exc))
    yield


app = FastAPI(
    title="Google Native Multi-Agent Life Ops System",
    version="0.1.0",
    lifespan=lifespan,
)


CHAT_UI_HTML = """
<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1.0" />
  <title>Life Ops Agent</title>
  <style>
    :root {
      --bg: #f3efe7;
      --panel: rgba(255, 252, 246, 0.92);
      --text: #1b1a17;
      --muted: #6b675f;
      --accent: #0c6c5a;
      --accent-2: #d66a3d;
      --border: rgba(27, 26, 23, 0.08);
      --shadow: 0 18px 50px rgba(25, 22, 17, 0.10);
    }

    * { box-sizing: border-box; }
    body {
      margin: 0;
      font-family: Georgia, "Iowan Old Style", "Palatino Linotype", serif;
      color: var(--text);
      background:
        radial-gradient(circle at top left, rgba(214, 106, 61, 0.18), transparent 32%),
        radial-gradient(circle at right 20%, rgba(12, 108, 90, 0.18), transparent 28%),
        linear-gradient(180deg, #f8f4ec 0%, var(--bg) 100%);
      min-height: 100vh;
    }

    .shell {
      max-width: 980px;
      margin: 0 auto;
      padding: 32px 20px 48px;
    }

    .hero {
      margin-bottom: 24px;
    }

    .eyebrow {
      display: inline-block;
      padding: 6px 10px;
      border-radius: 999px;
      background: rgba(12, 108, 90, 0.08);
      color: var(--accent);
      font-size: 12px;
      letter-spacing: 0.08em;
      text-transform: uppercase;
    }

    h1 {
      margin: 14px 0 10px;
      font-size: clamp(2.2rem, 5vw, 4.6rem);
      line-height: 0.95;
      max-width: 10ch;
    }

    .subhead {
      max-width: 56ch;
      font-size: 1.05rem;
      color: var(--muted);
      line-height: 1.6;
    }

    .layout {
      display: grid;
      grid-template-columns: 1.2fr 0.8fr;
      gap: 20px;
      align-items: start;
    }

    .panel {
      background: var(--panel);
      border: 1px solid var(--border);
      border-radius: 24px;
      box-shadow: var(--shadow);
      backdrop-filter: blur(18px);
    }

    .chat-panel {
      padding: 22px;
    }

    .messages {
      display: flex;
      flex-direction: column;
      gap: 14px;
      min-height: 420px;
      max-height: 62vh;
      overflow-y: auto;
      padding-right: 4px;
    }

    .bubble {
      padding: 14px 16px;
      border-radius: 18px;
      white-space: pre-wrap;
      line-height: 1.55;
      animation: rise 180ms ease-out;
    }

    .user {
      align-self: flex-end;
      background: #1d443d;
      color: #f8f4ec;
      border-bottom-right-radius: 6px;
      max-width: 78%;
    }

    .agent {
      align-self: flex-start;
      background: #fff9f0;
      border: 1px solid rgba(27, 26, 23, 0.08);
      border-bottom-left-radius: 6px;
      max-width: 86%;
    }

    .composer {
      margin-top: 18px;
      display: grid;
      grid-template-columns: 1fr auto;
      gap: 12px;
    }

    textarea {
      width: 100%;
      min-height: 82px;
      resize: vertical;
      border: 1px solid var(--border);
      border-radius: 18px;
      padding: 14px 16px;
      font: inherit;
      background: rgba(255, 255, 255, 0.8);
      color: var(--text);
    }

    button {
      border: 0;
      border-radius: 18px;
      padding: 0 22px;
      min-width: 128px;
      font: inherit;
      font-weight: 600;
      background: linear-gradient(135deg, var(--accent), #0e8a71);
      color: white;
      cursor: pointer;
      transition: transform 120ms ease, opacity 120ms ease;
    }

    button:hover { transform: translateY(-1px); }
    button:disabled { opacity: 0.6; cursor: wait; transform: none; }

    .side-panel {
      padding: 22px;
    }

    .card-title {
      margin: 0 0 12px;
      font-size: 1.1rem;
    }

    .hint-list, .tool-list {
      margin: 0;
      padding-left: 18px;
      color: var(--muted);
      line-height: 1.7;
    }

    .tool-box {
      margin-top: 18px;
      padding: 14px;
      border-radius: 18px;
      background: rgba(12, 108, 90, 0.05);
      border: 1px solid rgba(12, 108, 90, 0.08);
      min-height: 160px;
      overflow: auto;
    }

    .status {
      margin-top: 10px;
      color: var(--muted);
      font-size: 0.95rem;
    }

    .tool-entry {
      padding: 10px 0;
      border-bottom: 1px solid rgba(27, 26, 23, 0.08);
      font-family: ui-monospace, SFMono-Regular, Menlo, monospace;
      font-size: 0.85rem;
      color: #33413c;
    }

    .tool-entry:last-child { border-bottom: 0; }

    @keyframes rise {
      from { opacity: 0; transform: translateY(6px); }
      to { opacity: 1; transform: translateY(0); }
    }

    @media (max-width: 900px) {
      .layout { grid-template-columns: 1fr; }
      .messages { max-height: 48vh; }
      button { min-height: 56px; }
      .composer { grid-template-columns: 1fr; }
    }
  </style>
</head>
<body>
  <main class="shell">
    <section class="hero">
      <span class="eyebrow">Google Native Life Ops</span>
      <h1>Chat with your planner.</h1>
      <p class="subhead">
        Test tasks, notes, schedules, and multi-step planning from one browser tab.
        The panel on the right shows which MCP-style tools the agent used for each response.
      </p>
    </section>

    <section class="layout">
      <div class="panel chat-panel">
        <div id="messages" class="messages">
          <div class="bubble agent">Try: "Add task: study for exam Friday", "I have a meeting tomorrow at 3", or "Plan my day".</div>
        </div>
        <form id="chat-form" class="composer">
          <textarea id="message-input" placeholder="Tell the agent what you need..." required></textarea>
          <button id="send-button" type="submit">Send</button>
        </form>
        <div id="status" class="status">Ready.</div>
      </div>

      <aside class="panel side-panel">
        <h2 class="card-title">Suggested Prompts</h2>
        <ul class="hint-list">
          <li>Add task: study for exam Friday</li>
          <li>I have a meeting tomorrow at 3</li>
          <li>Store note: ask professor about the rubric</li>
          <li>Plan my day</li>
        </ul>

        <h2 class="card-title" style="margin-top: 24px;">Tool Trace</h2>
        <div id="tool-box" class="tool-box">
          <div class="tool-entry">No tool calls yet.</div>
        </div>
      </aside>
    </section>
  </main>

  <script>
    const form = document.getElementById("chat-form");
    const input = document.getElementById("message-input");
    const messages = document.getElementById("messages");
    const statusNode = document.getElementById("status");
    const sendButton = document.getElementById("send-button");
    const toolBox = document.getElementById("tool-box");

    let sessionId = null;

    function addMessage(text, role) {
      const bubble = document.createElement("div");
      bubble.className = `bubble ${role}`;
      bubble.textContent = text;
      messages.appendChild(bubble);
      messages.scrollTop = messages.scrollHeight;
    }

    function renderToolCalls(toolCalls) {
      toolBox.innerHTML = "";
      if (!toolCalls || toolCalls.length === 0) {
        toolBox.innerHTML = '<div class="tool-entry">No tool calls for this response.</div>';
        return;
      }

      toolCalls.forEach((call) => {
        const entry = document.createElement("div");
        entry.className = "tool-entry";
        entry.textContent = JSON.stringify(call, null, 2);
        toolBox.appendChild(entry);
      });
    }

    form.addEventListener("submit", async (event) => {
      event.preventDefault();
      const message = input.value.trim();
      if (!message) return;

      addMessage(message, "user");
      input.value = "";
      sendButton.disabled = true;
      statusNode.textContent = "Agent is thinking...";

      try {
        const response = await fetch("/query", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ message, session_id: sessionId }),
        });

        const data = await response.json();
        if (!response.ok) {
          throw new Error(data.detail || "Request failed.");
        }

        sessionId = data.session_id;
        addMessage(data.response, "agent");
        renderToolCalls(data.tool_calls);
        statusNode.textContent = "Done.";
      } catch (error) {
        addMessage(`Error: ${error.message}`, "agent");
        statusNode.textContent = "Request failed.";
      } finally {
        sendButton.disabled = false;
        input.focus();
      }
    });
  </script>
</body>
</html>
"""


@app.middleware("http")
async def request_logging_middleware(request: Request, call_next):
    request_id = request.headers.get("x-request-id", str(uuid4()))
    log_structured(
        logger,
        logging.INFO,
        "request_started",
        request_id=request_id,
        method=request.method,
        path=request.url.path,
    )
    response = await call_next(request)
    response.headers["x-request-id"] = request_id
    log_structured(
        logger,
        logging.INFO,
        "request_completed",
        request_id=request_id,
        method=request.method,
        path=request.url.path,
        status_code=response.status_code,
    )
    return response


@app.get("/", response_class=HTMLResponse)
async def index() -> HTMLResponse:
    return HTMLResponse(CHAT_UI_HTML)


@app.get("/health")
async def health() -> dict[str, str]:
    return {"status": "ok"}


@app.post("/query", response_model=QueryResponse)
async def query_agent(payload: QueryRequest) -> QueryResponse:
    try:
        result = await get_agent_service().query(
            message=payload.message,
            user_id=payload.user_id,
            session_id=payload.session_id,
        )
    except ToolExecutionError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc
    return QueryResponse(**result)


@app.get("/tasks")
async def list_tasks() -> dict[str, Any]:
    try:
        return get_tasks_bq()
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@app.get("/notes")
async def list_notes() -> dict[str, Any]:
    try:
        return get_notes_bq()
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@app.get("/events")
async def list_events() -> dict[str, Any]:
    try:
        return get_calendar_events()
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc
