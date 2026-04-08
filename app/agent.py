from __future__ import annotations

import logging
from uuid import uuid4

from google.adk.agents import LlmAgent
from google.adk.runners import Runner
from google.adk.sessions import InMemorySessionService
from google.adk.tools.agent_tool import AgentTool
from google.genai import types

from app.config.settings import get_settings, log_structured
from app.tools.bq_tools import create_task_bq, get_notes_bq, get_tasks_bq, store_note_bq
from app.tools.calendar_tools import create_calendar_event, get_calendar_events
from app.tools.common import get_tool_trace, start_tool_trace

logger = logging.getLogger(__name__)

APP_NAME = "life_ops"


ROOT_INSTRUCTION = """
You are the root coordinator for a life operations system.

Rules:
- Never invent tasks, notes, or calendar events.
- Always use tools or delegated agents for any external data operation.
- If a date or time is ambiguous, ask a concise follow-up question.
- For "plan my day", gather tasks and calendar events first, then produce a practical plan with suggested time blocks.
- Do not create calendar events while planning unless the user explicitly asks you to schedule something.
- Keep responses concise, structured, and action-oriented.
"""


TASK_AGENT_INSTRUCTION = """
You manage tasks only.
Use task tools for creating and fetching tasks in BigQuery.
Never mention calendar details unless the root agent asks for task context.
"""


CALENDAR_AGENT_INSTRUCTION = """
You manage scheduling only.
Use calendar tools for creating and fetching Google Calendar events.
If the user does not provide a clear time, ask a concise follow-up question.
"""


NOTES_AGENT_INSTRUCTION = """
You manage notes only.
Use note tools for storing and retrieving notes in BigQuery.
"""


def build_agent_system() -> LlmAgent:
    settings = get_settings()

    task_agent = LlmAgent(
        name="task_agent",
        model=settings.model_name,
        instruction=TASK_AGENT_INSTRUCTION,
        tools=[create_task_bq, get_tasks_bq],
    )
    calendar_agent = LlmAgent(
        name="calendar_agent",
        model=settings.model_name,
        instruction=CALENDAR_AGENT_INSTRUCTION,
        tools=[create_calendar_event, get_calendar_events],
    )
    notes_agent = LlmAgent(
        name="notes_agent",
        model=settings.model_name,
        instruction=NOTES_AGENT_INSTRUCTION,
        tools=[store_note_bq, get_notes_bq],
    )

    return LlmAgent(
        name="root_agent",
        model=settings.model_name,
        instruction=ROOT_INSTRUCTION,
        tools=[
            AgentTool(agent=task_agent, skip_summarization=False),
            AgentTool(agent=calendar_agent, skip_summarization=False),
            AgentTool(agent=notes_agent, skip_summarization=False),
            get_tasks_bq,
            get_calendar_events,
            get_notes_bq,
        ],
    )


class LifeOpsAgentService:
    """Thin wrapper around ADK runner/session handling."""

    def __init__(self) -> None:
        self._root_agent = build_agent_system()
        self._sessions = InMemorySessionService()
        self._runner = Runner(
            app_name=APP_NAME,
            agent=self._root_agent,
            session_service=self._sessions,
        )

    async def query(
        self,
        message: str,
        user_id: str | None = None,
        session_id: str | None = None,
    ) -> dict[str, object]:
        active_user_id = user_id or "default-user"
        active_session_id = session_id or str(uuid4())
        trace_id = start_tool_trace()

        session = await self._sessions.get_session(
            app_name=APP_NAME,
            user_id=active_user_id,
            session_id=active_session_id,
        )
        if session is None:
            await self._sessions.create_session(
                app_name=APP_NAME,
                user_id=active_user_id,
                session_id=active_session_id,
            )

        log_structured(
            logger,
            logging.INFO,
            "agent_query_started",
            user_id=active_user_id,
            session_id=active_session_id,
            trace_id=trace_id,
        )

        content = types.Content(role="user", parts=[types.Part(text=message)])
        events = []
        async for event in self._runner.run_async(
            user_id=active_user_id,
            session_id=active_session_id,
            new_message=content,
        ):
            events.append(event)

        response_text = self._extract_response_text(events)
        tool_calls = get_tool_trace()

        log_structured(
            logger,
            logging.INFO,
            "agent_query_completed",
            user_id=active_user_id,
            session_id=active_session_id,
            trace_id=trace_id,
            tool_call_count=len(tool_calls),
        )
        return {
            "response": response_text,
            "tool_calls": tool_calls,
            "session_id": active_session_id,
        }

    @staticmethod
    def _extract_response_text(events: list[object]) -> str:
        messages: list[str] = []
        for event in events:
            content = getattr(event, "content", None)
            if content is None:
                continue
            parts = getattr(content, "parts", None) or []
            for part in parts:
                text = getattr(part, "text", None)
                if text:
                    messages.append(text)
        return "\n".join(messages).strip() or "No response generated."


_service: LifeOpsAgentService | None = None


def get_agent_service() -> LifeOpsAgentService:
    global _service
    if _service is None:
        _service = LifeOpsAgentService()
    return _service
