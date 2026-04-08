from __future__ import annotations

import inspect
import json
import logging
import time
from contextvars import ContextVar
from dataclasses import dataclass
from datetime import UTC, datetime
from functools import wraps
from typing import Any, Callable, ParamSpec, TypeVar
from uuid import uuid4
from zoneinfo import ZoneInfo

import dateparser

from app.config.settings import get_settings, log_structured

P = ParamSpec("P")
R = TypeVar("R")

logger = logging.getLogger(__name__)

_tool_call_context: ContextVar[list[dict[str, Any]]] = ContextVar(
    "tool_call_context",
    default=[],
)


class ToolExecutionError(RuntimeError):
    """Raised when a tool cannot complete its action safely."""


@dataclass(slots=True)
class ToolContext:
    request_id: str


def start_tool_trace(request_id: str | None = None) -> str:
    trace_id = request_id or str(uuid4())
    _tool_call_context.set([])
    return trace_id


def get_tool_trace() -> list[dict[str, Any]]:
    return list(_tool_call_context.get())


def append_tool_trace(payload: dict[str, Any]) -> None:
    current = list(_tool_call_context.get())
    current.append(payload)
    _tool_call_context.set(current)


def serialize_for_log(value: Any) -> Any:
    if isinstance(value, datetime):
        return value.isoformat()
    if isinstance(value, (str, int, float, bool)) or value is None:
        return value
    if isinstance(value, dict):
        return {key: serialize_for_log(item) for key, item in value.items()}
    if isinstance(value, list):
        return [serialize_for_log(item) for item in value]
    return str(value)


def tool_logger(name: str) -> Callable[[Callable[P, R]], Callable[P, R]]:
    """Decorate sync or async tool functions with structured logging and tracing."""

    def decorator(func: Callable[P, R]) -> Callable[P, R]:
        is_coroutine = inspect.iscoroutinefunction(func)
        signature = inspect.signature(func)

        def _bound_arguments(*args: P.args, **kwargs: P.kwargs) -> dict[str, Any]:
            bound = signature.bind_partial(*args, **kwargs)
            bound.apply_defaults()
            return {
                key: value
                for key, value in bound.arguments.items()
                if key not in {"self", "cls"}
            }

        @wraps(func)
        async def async_wrapper(*args: P.args, **kwargs: P.kwargs) -> R:
            started = time.perf_counter()
            arguments = _bound_arguments(*args, **kwargs)
            try:
                result = await func(*args, **kwargs)
            except Exception as exc:
                elapsed_ms = round((time.perf_counter() - started) * 1000, 2)
                payload = {
                    "tool": name,
                    "status": "error",
                    "elapsed_ms": elapsed_ms,
                    "error": str(exc),
                    "args": serialize_for_log(arguments),
                }
                append_tool_trace(payload)
                log_structured(logger, logging.ERROR, "tool_error", **payload)
                raise

            elapsed_ms = round((time.perf_counter() - started) * 1000, 2)
            payload = {
                "tool": name,
                "status": "ok",
                "elapsed_ms": elapsed_ms,
                "args": serialize_for_log(arguments),
                "result": serialize_for_log(result),
            }
            append_tool_trace(payload)
            log_structured(logger, logging.INFO, "tool_call", **payload)
            return result

        @wraps(func)
        def sync_wrapper(*args: P.args, **kwargs: P.kwargs) -> R:
            started = time.perf_counter()
            arguments = _bound_arguments(*args, **kwargs)
            try:
                result = func(*args, **kwargs)
            except Exception as exc:
                elapsed_ms = round((time.perf_counter() - started) * 1000, 2)
                payload = {
                    "tool": name,
                    "status": "error",
                    "elapsed_ms": elapsed_ms,
                    "error": str(exc),
                    "args": serialize_for_log(arguments),
                }
                append_tool_trace(payload)
                log_structured(logger, logging.ERROR, "tool_error", **payload)
                raise

            elapsed_ms = round((time.perf_counter() - started) * 1000, 2)
            payload = {
                "tool": name,
                "status": "ok",
                "elapsed_ms": elapsed_ms,
                "args": serialize_for_log(arguments),
                "result": serialize_for_log(result),
            }
            append_tool_trace(payload)
            log_structured(logger, logging.INFO, "tool_call", **payload)
            return result

        if is_coroutine:
            return async_wrapper
        return sync_wrapper

    return decorator


def utcnow() -> datetime:
    return datetime.now(UTC)


def ensure_timezone(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=UTC)
    return value


def parse_user_datetime(value: str | None) -> datetime | None:
    if value is None or not value.strip():
        return None

    settings = get_settings()
    parsed = dateparser.parse(
        value,
        settings={
            "TIMEZONE": settings.service_timezone,
            "RETURN_AS_TIMEZONE_AWARE": True,
            "PREFER_DATES_FROM": "future",
        },
    )
    if parsed is None:
        raise ToolExecutionError(
            "Could not parse the provided date/time. Please provide a specific date or time."
        )
    return ensure_timezone(parsed.astimezone(UTC))


def get_service_timezone() -> ZoneInfo:
    return ZoneInfo(get_settings().service_timezone)


def to_service_timezone(value: datetime | None) -> datetime | None:
    if value is None:
        return None
    return ensure_timezone(value).astimezone(get_service_timezone())


def format_local_datetime(value: datetime | None) -> str | None:
    localized = to_service_timezone(value)
    if localized is None:
        return None
    return localized.strftime("%Y-%m-%d %H:%M %Z")


def sanitize_text(value: str, max_length: int = 500) -> str:
    cleaned = " ".join(value.split())
    return cleaned[:max_length]


def dumps_json(value: Any) -> str:
    return json.dumps(value, default=str)
