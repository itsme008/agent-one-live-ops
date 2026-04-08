from __future__ import annotations

from app.main import QueryRequest, QueryResponse


def test_query_request_accepts_message() -> None:
    payload = QueryRequest(message="Plan my day")
    assert payload.message == "Plan my day"


def test_query_response_round_trip() -> None:
    response = QueryResponse(
        response="Here's your plan.",
        tool_calls=[{"tool": "get_tasks_bq", "status": "ok"}],
        session_id="session-123",
    )
    assert response.session_id == "session-123"
