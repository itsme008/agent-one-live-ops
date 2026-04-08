from __future__ import annotations

import logging
from contextlib import asynccontextmanager
from typing import Any
from uuid import uuid4

from fastapi import FastAPI, HTTPException, Request
from pydantic import BaseModel, Field

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
