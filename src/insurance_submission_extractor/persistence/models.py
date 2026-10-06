"""Relational schema for extraction and evaluation history.

Tables hold metadata and outcomes only. They never contain submission text,
extracted values, or evidence excerpts.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any

from sqlalchemy import JSON, Boolean, DateTime, Float, ForeignKey, Integer, String
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship

JSON_TYPE = JSON().with_variant(JSONB(), "postgresql")


class Base(DeclarativeBase):
    pass


class ExtractionRunRow(Base):
    __tablename__ = "extraction_runs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    recorded_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    submission_id: Mapped[str] = mapped_column(String(255), index=True)
    correlation_id: Mapped[str | None] = mapped_column(String(255), index=True)
    status: Mapped[str] = mapped_column(String(16))
    provider: Mapped[str] = mapped_column(String(64), index=True)
    model: Mapped[str] = mapped_column(String(128))
    duration_ms: Mapped[float] = mapped_column(Float)
    fallback_used: Mapped[bool] = mapped_column(Boolean)
    review_required: Mapped[bool | None] = mapped_column(Boolean)
    missing_field_count: Mapped[int | None] = mapped_column(Integer)
    unsupported_fields: Mapped[list[Any]] = mapped_column(JSON_TYPE)
    error_type: Mapped[str | None] = mapped_column(String(128))
    input_tokens: Mapped[int | None] = mapped_column(Integer)
    output_tokens: Mapped[int | None] = mapped_column(Integer)
    cost_usd: Mapped[float | None] = mapped_column(Float)
    llm_calls: Mapped[int | None] = mapped_column(Integer)
    failed_llm_calls: Mapped[int | None] = mapped_column(Integer)
    attempts: Mapped[list[Any]] = mapped_column(JSON_TYPE)


class EvaluationRunRow(Base):
    __tablename__ = "evaluation_runs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    evaluated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    system: Mapped[str] = mapped_column(String(128), index=True)
    model: Mapped[str] = mapped_column(String(128))
    dataset: Mapped[str] = mapped_column(String(512))
    total_cases: Mapped[int] = mapped_column(Integer)
    passed_cases: Mapped[int] = mapped_column(Integer)
    failed_cases: Mapped[int] = mapped_column(Integer)
    errored_cases: Mapped[int] = mapped_column(Integer)
    pass_rate: Mapped[float] = mapped_column(Float)
    missing_field_recall: Mapped[float | None] = mapped_column(Float)
    hallucination_rate: Mapped[float | None] = mapped_column(Float)
    by_family: Mapped[dict[str, Any]] = mapped_column(JSON_TYPE)
    field_metrics: Mapped[dict[str, Any]] = mapped_column(JSON_TYPE)

    cases: Mapped[list[EvaluationCaseRow]] = relationship(
        back_populates="run", cascade="all, delete-orphan", order_by="EvaluationCaseRow.id"
    )


class EvaluationCaseRow(Base):
    __tablename__ = "evaluation_cases"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    run_id: Mapped[int] = mapped_column(
        ForeignKey("evaluation_runs.id", ondelete="CASCADE"), index=True
    )
    case_id: Mapped[str] = mapped_column(String(255), index=True)
    family: Mapped[str] = mapped_column(String(128), index=True)
    passed: Mapped[bool] = mapped_column(Boolean)
    duration_ms: Mapped[float | None] = mapped_column(Float)
    failures: Mapped[list[Any]] = mapped_column(JSON_TYPE)
    checks: Mapped[dict[str, Any]] = mapped_column(JSON_TYPE)
    hallucinated_fields: Mapped[list[Any]] = mapped_column(JSON_TYPE)

    run: Mapped[EvaluationRunRow] = relationship(back_populates="cases")
