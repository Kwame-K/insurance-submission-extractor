"""Database storage for extraction records and evaluation reports.

Works with SQLite and PostgreSQL through SQLAlchemy. Schema changes are managed
with Alembic migrations that ship inside this package.
"""

from __future__ import annotations

import threading
from datetime import datetime
from pathlib import Path
from typing import Any

from alembic import command
from alembic.config import Config
from sqlalchemy import Engine, create_engine, select
from sqlalchemy.engine import make_url
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

from insurance_submission_extractor.persistence.models import (
    EvaluationCaseRow,
    EvaluationRunRow,
    ExtractionRunRow,
)
from insurance_submission_extractor.services.telemetry import ExtractionLogRecord

MIGRATIONS_DIRECTORY = Path(__file__).resolve().parent / "migrations"


def normalize_database_url(url: str) -> str:
    """Point plain PostgreSQL URLs at the installed psycopg 3 driver."""
    for prefix in ("postgresql://", "postgres://"):
        if url.startswith(prefix):
            return "postgresql+psycopg://" + url[len(prefix) :]

    return url


def _create_engine(url: str) -> Engine:
    parsed = make_url(url)

    if parsed.get_backend_name() == "sqlite":
        options: dict[str, Any] = {"connect_args": {"check_same_thread": False}}
        if parsed.database in (None, "", ":memory:"):
            options["poolclass"] = StaticPool

        return create_engine(url, **options)

    return create_engine(url, pool_pre_ping=True)


def case_family(case_id: str) -> str:
    """Return the scenario family of a generated case id, or 'base'."""
    if case_id.startswith("gen_"):
        return case_id.removeprefix("gen_").rsplit("_", 1)[0]

    return "base"


class DatabaseStore:
    def __init__(self, url: str, *, auto_migrate: bool = True) -> None:
        self._engine = _create_engine(normalize_database_url(url))
        self._auto_migrate = auto_migrate
        self._ready = not auto_migrate
        self._lock = threading.Lock()

    @property
    def engine(self) -> Engine:
        return self._engine

    def migrate(self) -> None:
        """Bring the database schema up to the latest revision."""
        config = Config()
        config.set_main_option("script_location", str(MIGRATIONS_DIRECTORY))

        with self._engine.begin() as connection:
            config.attributes["connection"] = connection
            command.upgrade(config, "head")

    def _ensure_ready(self) -> None:
        if self._ready:
            return

        with self._lock:
            if not self._ready:
                self.migrate()
                self._ready = True

    def save_extraction(self, record: ExtractionLogRecord) -> None:
        self._ensure_ready()
        row = ExtractionRunRow(
            recorded_at=record.timestamp,
            submission_id=record.submission_id,
            correlation_id=record.correlation_id,
            status=record.status,
            provider=record.provider,
            model=record.model,
            duration_ms=record.duration_ms,
            fallback_used=record.fallback_used,
            review_required=record.review_required,
            missing_field_count=record.missing_field_count,
            unsupported_fields=list(record.unsupported_fields),
            error_type=record.error_type,
            input_tokens=record.input_tokens,
            output_tokens=record.output_tokens,
            cost_usd=record.cost_usd,
            llm_calls=record.llm_calls,
            failed_llm_calls=record.failed_llm_calls,
            attempts=[attempt.model_dump() for attempt in record.attempts],
        )

        with Session(self._engine) as session, session.begin():
            session.add(row)

    def save_evaluation(self, report: dict[str, Any]) -> int:
        """Store an evaluation report's outcomes (not the extracted data). Returns the run id."""
        self._ensure_ready()
        summary = report["summary"]
        metrics = report.get("field_metrics") or {}
        run = EvaluationRunRow(
            evaluated_at=datetime.fromisoformat(report["evaluated_at"]),
            system=report["provider"],
            model=report["model"],
            dataset=report["dataset"],
            total_cases=summary["total_cases"],
            passed_cases=summary["passed_cases"],
            failed_cases=summary["failed_cases"],
            errored_cases=summary["errored_cases"],
            pass_rate=summary["pass_rate"],
            missing_field_recall=metrics.get("missing_field_recall"),
            hallucination_rate=(metrics.get("hallucination") or {}).get("rate"),
            by_family=summary.get("by_family", {}),
            field_metrics=metrics.get("fields", {}),
        )
        for case in report["cases"]:
            evaluation = case["evaluation"]
            run.cases.append(
                EvaluationCaseRow(
                    case_id=case["case_id"],
                    family=case_family(case["case_id"]),
                    passed=evaluation["passed"],
                    duration_ms=case.get("duration_ms"),
                    failures=list(evaluation.get("failures", [])),
                    checks=dict(evaluation.get("checks", {})),
                    hallucinated_fields=list(evaluation.get("hallucinated_fields", [])),
                )
            )

        with Session(self._engine) as session, session.begin():
            session.add(run)
            session.flush()
            run_id = run.id

        return run_id

    def extraction_records(self) -> list[dict[str, Any]]:
        """Return extraction rows in the same shape as the JSONL log records."""
        self._ensure_ready()
        with Session(self._engine) as session:
            rows = session.scalars(select(ExtractionRunRow).order_by(ExtractionRunRow.id)).all()

            return [
                {
                    "event": "extraction",
                    "timestamp": row.recorded_at.isoformat(),
                    "submission_id": row.submission_id,
                    "correlation_id": row.correlation_id,
                    "status": row.status,
                    "provider": row.provider,
                    "model": row.model,
                    "duration_ms": row.duration_ms,
                    "fallback_used": row.fallback_used,
                    "review_required": row.review_required,
                    "missing_field_count": row.missing_field_count,
                    "unsupported_fields": list(row.unsupported_fields or []),
                    "error_type": row.error_type,
                    "input_tokens": row.input_tokens,
                    "output_tokens": row.output_tokens,
                    "cost_usd": row.cost_usd,
                    "llm_calls": row.llm_calls,
                    "failed_llm_calls": row.failed_llm_calls,
                    "attempts": list(row.attempts or []),
                }
                for row in rows
            ]

    def evaluation_runs(self) -> list[dict[str, Any]]:
        """Return one summary per stored evaluation run, oldest first."""
        self._ensure_ready()
        with Session(self._engine) as session:
            statement = select(EvaluationRunRow).order_by(
                EvaluationRunRow.evaluated_at, EvaluationRunRow.id
            )
            rows = session.scalars(statement).all()

            return [
                {
                    "id": row.id,
                    "evaluated_at": row.evaluated_at.isoformat(),
                    "system": row.system,
                    "model": row.model,
                    "dataset": row.dataset,
                    "total_cases": row.total_cases,
                    "passed_cases": row.passed_cases,
                    "pass_rate": row.pass_rate,
                    "errored_cases": row.errored_cases,
                    "missing_field_recall": row.missing_field_recall,
                    "hallucination_rate": row.hallucination_rate,
                }
                for row in rows
            ]

    def close(self) -> None:
        self._engine.dispose()
