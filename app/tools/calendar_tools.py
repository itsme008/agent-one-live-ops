from __future__ import annotations

import logging
from datetime import timedelta
from typing import Any

from googleapiclient.discovery import build

from app.config.settings import get_settings, validate_required_gcp_settings
from app.tools.common import ToolExecutionError, parse_user_datetime, sanitize_text, tool_logger, utcnow

logger = logging.getLogger(__name__)


def get_calendar_service():
    validate_required_gcp_settings()
    return build("calendar", "v3", cache_discovery=False)


def _event_to_payload(event: dict[str, Any]) -> dict[str, Any]:
    start = event.get("start", {})
    end = event.get("end", {})
    return {
        "id": event.get("id"),
        "title": event.get("summary"),
        "description": event.get("description"),
        "status": event.get("status"),
        "html_link": event.get("htmlLink"),
        "start": start.get("dateTime") or start.get("date"),
        "end": end.get("dateTime") or end.get("date"),
    }


@tool_logger("create_calendar_event")
def create_calendar_event(
    title: str,
    time: str,
    duration_minutes: int | None = None,
) -> dict[str, Any]:
    if not title.strip():
        raise ToolExecutionError("Calendar event title cannot be empty.")

    settings = get_settings()
    start = parse_user_datetime(time)
    if start is None:
        raise ToolExecutionError("A calendar event requires a start time.")
    duration = duration_minutes or settings.query_default_duration_minutes
    end = start + timedelta(minutes=duration)

    event_body = {
        "summary": sanitize_text(title, max_length=200),
        "start": {"dateTime": start.isoformat()},
        "end": {"dateTime": end.isoformat()},
    }

    event = (
        get_calendar_service()
        .events()
        .insert(calendarId=settings.calendar_id, body=event_body)
        .execute()
    )

    return {"status": "ok", "event": _event_to_payload(event)}


@tool_logger("get_calendar_events")
def get_calendar_events(
    time_min: str | None = None,
    time_max: str | None = None,
) -> dict[str, Any]:
    settings = get_settings()
    min_dt = parse_user_datetime(time_min) if time_min else utcnow()
    max_dt = parse_user_datetime(time_max) if time_max else None

    request = (
        get_calendar_service()
        .events()
        .list(
            calendarId=settings.calendar_id,
            timeMin=min_dt.isoformat(),
            timeMax=max_dt.isoformat() if max_dt else None,
            singleEvents=True,
            orderBy="startTime",
            maxResults=20,
        )
    )
    response = request.execute()
    events = [_event_to_payload(item) for item in response.get("items", [])]
    return {"status": "ok", "events": events}
