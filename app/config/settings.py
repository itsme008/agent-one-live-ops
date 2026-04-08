from __future__ import annotations

import json
import logging
import os
from functools import lru_cache
from typing import Any

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Runtime configuration loaded from environment variables."""

    google_cloud_project: str = Field(
        default_factory=lambda: os.getenv("GOOGLE_CLOUD_PROJECT", ""),
        alias="GOOGLE_CLOUD_PROJECT",
    )
    vertex_ai_location: str = Field(default="us-central1", alias="VERTEX_AI_LOCATION")
    bigquery_dataset: str = Field(default="life_ops", alias="BIGQUERY_DATASET")
    calendar_id: str = Field(default="primary", alias="CALENDAR_ID")
    service_timezone: str = Field(default="UTC", alias="SERVICE_TIMEZONE")
    log_level: str = Field(default="INFO", alias="LOG_LEVEL")
    app_name: str = Field(default="life-ops-api", alias="APP_NAME")
    model_name: str = Field(default="gemini-2.5-flash", alias="MODEL_NAME")
    query_default_duration_minutes: int = Field(
        default=60,
        alias="DEFAULT_EVENT_DURATION_MINUTES",
    )
    bootstrap_bigquery_on_startup: bool = Field(
        default=True,
        alias="BOOTSTRAP_BIGQUERY_ON_STARTUP",
    )

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
        populate_by_name=True,
    )

    @property
    def tasks_table(self) -> str:
        return f"{self.google_cloud_project}.{self.bigquery_dataset}.tasks"

    @property
    def notes_table(self) -> str:
        return f"{self.google_cloud_project}.{self.bigquery_dataset}.notes"


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings()


def configure_logging() -> None:
    """Set a consistent JSON-ish logging format for API and tool events."""
    settings = get_settings()
    level = getattr(logging, settings.log_level.upper(), logging.INFO)
    logging.basicConfig(
        level=level,
        format="%(message)s",
    )


def log_structured(
    logger: logging.Logger,
    level: int,
    message: str,
    **fields: Any,
) -> None:
    payload = {"message": message, **fields}
    logger.log(level, json.dumps(payload, default=str))


def validate_required_gcp_settings() -> None:
    settings = get_settings()
    if not settings.google_cloud_project:
        raise RuntimeError("GOOGLE_CLOUD_PROJECT is required.")
