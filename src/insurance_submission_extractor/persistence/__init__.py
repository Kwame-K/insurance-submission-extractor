"""Optional database persistence for extraction and evaluation history."""

from __future__ import annotations

from typing import Protocol

from insurance_submission_extractor.persistence.store import (
    DatabaseStore,
    normalize_database_url,
)

__all__ = ["DatabaseStore", "create_store", "normalize_database_url"]


class _DatabaseSettings(Protocol):
    database_url: str | None
    database_auto_migrate: bool


def create_store(settings: _DatabaseSettings) -> DatabaseStore | None:
    """Return a store when DATABASE_URL is configured, otherwise None (persistence off)."""
    if not settings.database_url:
        return None

    return DatabaseStore(settings.database_url, auto_migrate=settings.database_auto_migrate)
