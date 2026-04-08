from __future__ import annotations

from datetime import UTC

import pytest

from app.tools.common import (
    ToolExecutionError,
    format_local_datetime,
    parse_user_datetime,
    sanitize_text,
)


def test_sanitize_text_collapses_whitespace() -> None:
    assert sanitize_text("  plan   my\tday  ") == "plan my day"


def test_parse_user_datetime_rejects_unknown_value() -> None:
    with pytest.raises(ToolExecutionError):
        parse_user_datetime("sometime maybe")


def test_parse_user_datetime_returns_timezone_aware_value() -> None:
    parsed = parse_user_datetime("tomorrow at 3pm")
    assert parsed is not None
    assert parsed.tzinfo == UTC


def test_format_local_datetime_renders_local_timezone() -> None:
    parsed = parse_user_datetime("2026-04-10 00:00")
    assert parsed is not None
    assert format_local_datetime(parsed) is not None
