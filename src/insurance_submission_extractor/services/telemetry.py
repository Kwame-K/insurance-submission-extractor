"""Structured, content-free extraction logs and their summary.

Records hold metadata only (identifiers, provider, timings, counts, field names).
They never contain submission text, extracted values, or evidence excerpts.
"""

from __future__ import annotations

import json
import logging
import math
from collections import defaultdict
from contextvars import ContextVar
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Literal, Protocol

from pydantic import BaseModel, Field

LOGGER = logging.getLogger("insurance_submission_extractor.extraction")

CORRELATION_ID: ContextVar[str | None] = ContextVar("correlation_id", default=None)


class AttemptUsage(BaseModel):
    provider: str
    model: str
    input_tokens: int
    output_tokens: int


class ExtractionLogRecord(BaseModel):
    event: Literal["extraction"] = "extraction"
    timestamp: datetime = Field(default_factory=lambda: datetime.now(UTC))
    submission_id: str
    correlation_id: str | None = None
    status: Literal["ok", "error"]
    provider: str
    model: str
    duration_ms: float
    fallback_used: bool = False
    review_required: bool | None = None
    missing_field_count: int | None = None
    unsupported_fields: list[str] = Field(default_factory=list)
    error_type: str | None = None
    input_tokens: int | None = None
    output_tokens: int | None = None
    cost_usd: float | None = None
    llm_calls: int | None = None
    failed_llm_calls: int | None = None
    attempts: list[AttemptUsage] = Field(default_factory=list)


class ExtractionStore(Protocol):
    def save_extraction(self, record: ExtractionLogRecord) -> None: ...


def emit_extraction_log(
    record: ExtractionLogRecord,
    path: Path | None,
    store: ExtractionStore | None = None,
) -> None:
    """Log a record, append it to the JSONL file and store it in the database if configured.

    Logging and storage problems never interrupt an extraction.
    """
    line = record.model_dump_json()
    LOGGER.info(line)

    if store is not None:
        try:
            store.save_extraction(record)
        except Exception as error:
            LOGGER.warning(
                "Could not store the extraction record in the database (%s)",
                type(error).__name__,
            )

    if path is None:
        return

    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("a", encoding="utf-8") as handle:
            handle.write(line + "\n")
    except OSError:
        LOGGER.warning("Could not write extraction log to %s", path)


def read_records(path: Path) -> list[dict[str, Any]]:
    """Read JSONL records, skipping blank or malformed lines."""
    records: list[dict[str, Any]] = []

    for line in path.read_text(encoding="utf-8").splitlines():
        try:
            record = json.loads(line)
        except json.JSONDecodeError:
            continue
        if isinstance(record, dict) and record.get("event") == "extraction":
            records.append(record)

    return records


def _percentile(values: list[float], fraction: float) -> float:
    ordered = sorted(values)

    return ordered[max(0, math.ceil(fraction * len(ordered)) - 1)]


def _rate(count: int, total: int) -> float:
    return round(count / total, 4) if total else 0.0


def summarize_records(records: list[dict[str, Any]]) -> dict[str, Any]:
    """Aggregate rates and latency for a list of extraction log records."""
    total = len(records)
    ok = [record for record in records if record["status"] == "ok"]
    durations = [float(record["duration_ms"]) for record in records]

    by_provider: dict[str, list[float]] = defaultdict(list)
    for record in ok:
        by_provider[record["provider"]].append(float(record["duration_ms"]))

    unsupported_counts: dict[str, int] = defaultdict(int)
    for record in ok:
        for field_name in record.get("unsupported_fields", []):
            unsupported_counts[field_name] += 1

    with_calls = [r for r in records if r.get("llm_calls") is not None]
    with_usage = [r for r in ok if r.get("input_tokens") is not None]
    priced = [r for r in with_usage if r.get("cost_usd") is not None]

    return {
        "total_extractions": total,
        "error_rate": _rate(total - len(ok), total),
        "fallback_rate": _rate(sum(1 for r in ok if r.get("fallback_used")), len(ok)),
        "review_rate": _rate(sum(1 for r in ok if r.get("review_required")), len(ok)),
        "unsupported_value_rate": _rate(sum(1 for r in ok if r.get("unsupported_fields")), len(ok)),
        "latency_ms": (
            {
                "p50": round(_percentile(durations, 0.5), 1),
                "p95": round(_percentile(durations, 0.95), 1),
                "max": round(max(durations), 1),
            }
            if durations
            else {}
        ),
        "successful_by_provider": {
            provider: {
                "count": len(values),
                "p50_ms": round(_percentile(values, 0.5), 1),
                "p95_ms": round(_percentile(values, 0.95), 1),
            }
            for provider, values in sorted(by_provider.items())
        },
        "unsupported_by_field": dict(sorted(unsupported_counts.items())),
        "llm_calls": {
            "total": sum(r["llm_calls"] for r in with_calls),
            "failed": sum(r.get("failed_llm_calls") or 0 for r in with_calls),
            "mean_per_extraction": round(
                sum(r["llm_calls"] for r in with_calls) / len(with_calls), 3
            )
            if with_calls
            else None,
            "max_per_extraction": max((r["llm_calls"] for r in with_calls), default=None),
        },
        "tokens": {
            "extractions_with_usage": len(with_usage),
            "input_total": sum(r["input_tokens"] for r in with_usage),
            "output_total": sum(r["output_tokens"] for r in with_usage),
            "input_mean": round(sum(r["input_tokens"] for r in with_usage) / len(with_usage), 1)
            if with_usage
            else None,
            "output_mean": round(sum(r["output_tokens"] for r in with_usage) / len(with_usage), 1)
            if with_usage
            else None,
        },
        "cost_usd": {
            "priced_extractions": len(priced),
            "unpriced_extractions": len(with_usage) - len(priced),
            "total": round(sum(r["cost_usd"] for r in priced), 6),
            "mean_per_extraction": round(sum(r["cost_usd"] for r in priced) / len(priced), 6)
            if priced
            else None,
        },
    }
