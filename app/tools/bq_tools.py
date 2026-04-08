from __future__ import annotations

import logging
from typing import Any
from uuid import uuid4

from google.api_core.exceptions import NotFound
from google.cloud import bigquery

from app.config.settings import get_settings, log_structured, validate_required_gcp_settings
from app.tools.common import (
    ToolExecutionError,
    parse_user_datetime,
    sanitize_text,
    tool_logger,
    utcnow,
)

logger = logging.getLogger(__name__)


TASK_SCHEMA = [
    bigquery.SchemaField("id", "STRING", mode="REQUIRED"),
    bigquery.SchemaField("title", "STRING", mode="REQUIRED"),
    bigquery.SchemaField("deadline", "TIMESTAMP", mode="NULLABLE"),
    bigquery.SchemaField("created_at", "TIMESTAMP", mode="REQUIRED"),
]

NOTES_SCHEMA = [
    bigquery.SchemaField("id", "STRING", mode="REQUIRED"),
    bigquery.SchemaField("content", "STRING", mode="REQUIRED"),
    bigquery.SchemaField("created_at", "TIMESTAMP", mode="REQUIRED"),
]


def get_bigquery_client() -> bigquery.Client:
    validate_required_gcp_settings()
    settings = get_settings()
    return bigquery.Client(project=settings.google_cloud_project)


def _dataset_ref() -> str:
    settings = get_settings()
    return f"{settings.google_cloud_project}.{settings.bigquery_dataset}"


def _ensure_table(
    client: bigquery.Client,
    table_name: str,
    schema: list[bigquery.SchemaField],
) -> None:
    settings = get_settings()
    table_id = f"{settings.google_cloud_project}.{settings.bigquery_dataset}.{table_name}"
    try:
        client.get_table(table_id)
        return
    except NotFound:
        table = bigquery.Table(table_id, schema=schema)
        client.create_table(table)
        log_structured(logger, logging.INFO, "bigquery_table_created", table_id=table_id)


def bootstrap_bigquery() -> dict[str, Any]:
    client = get_bigquery_client()
    dataset_id = _dataset_ref()
    try:
        client.get_dataset(dataset_id)
    except NotFound:
        dataset = bigquery.Dataset(dataset_id)
        dataset.location = get_settings().vertex_ai_location
        client.create_dataset(dataset)
        log_structured(logger, logging.INFO, "bigquery_dataset_created", dataset_id=dataset_id)

    _ensure_table(client, "tasks", TASK_SCHEMA)
    _ensure_table(client, "notes", NOTES_SCHEMA)
    return {"status": "ok", "dataset": dataset_id, "tables": ["tasks", "notes"]}


@tool_logger("create_task_bq")
def create_task_bq(title: str, deadline: str | None = None) -> dict[str, Any]:
    if not title.strip():
        raise ToolExecutionError("Task title cannot be empty.")

    client = get_bigquery_client()
    settings = get_settings()
    task_id = str(uuid4())
    parsed_deadline = parse_user_datetime(deadline) if deadline else None
    row = {
        "id": task_id,
        "title": sanitize_text(title, max_length=200),
        "deadline": parsed_deadline.isoformat() if parsed_deadline else None,
        "created_at": utcnow().isoformat(),
    }
    errors = client.insert_rows_json(settings.tasks_table, [row])
    if errors:
        raise ToolExecutionError(f"Failed to insert task into BigQuery: {errors}")

    return {"status": "ok", "task": row}


@tool_logger("get_tasks_bq")
def get_tasks_bq() -> dict[str, Any]:
    client = get_bigquery_client()
    settings = get_settings()
    query = f"""
        SELECT id, title, deadline, created_at
        FROM `{settings.tasks_table}`
        ORDER BY deadline IS NULL, deadline, created_at DESC
    """
    rows = client.query(query).result()
    tasks = [
        {
            "id": row["id"],
            "title": row["title"],
            "deadline": row["deadline"].isoformat() if row["deadline"] else None,
            "created_at": row["created_at"].isoformat(),
        }
        for row in rows
    ]
    return {"status": "ok", "tasks": tasks}


@tool_logger("store_note_bq")
def store_note_bq(content: str) -> dict[str, Any]:
    if not content.strip():
        raise ToolExecutionError("Note content cannot be empty.")

    client = get_bigquery_client()
    settings = get_settings()
    note_id = str(uuid4())
    row = {
        "id": note_id,
        "content": sanitize_text(content, max_length=5000),
        "created_at": utcnow().isoformat(),
    }
    errors = client.insert_rows_json(settings.notes_table, [row])
    if errors:
        raise ToolExecutionError(f"Failed to insert note into BigQuery: {errors}")
    return {"status": "ok", "note": row}


@tool_logger("get_notes_bq")
def get_notes_bq() -> dict[str, Any]:
    client = get_bigquery_client()
    settings = get_settings()
    query = f"""
        SELECT id, content, created_at
        FROM `{settings.notes_table}`
        ORDER BY created_at DESC
    """
    rows = client.query(query).result()
    notes = [
        {
            "id": row["id"],
            "content": row["content"],
            "created_at": row["created_at"].isoformat(),
        }
        for row in rows
    ]
    return {"status": "ok", "notes": notes}
