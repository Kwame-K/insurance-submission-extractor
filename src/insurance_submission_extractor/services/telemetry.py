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
from typing import Any, Literal

from pydantic import BaseModel, Field

LOGGER = logging.getLogger("insurance_submission_extractor.extraction")

CORRELATION_ID: ContextVar[str | None] = ContextVar("correlation_id", default=None)


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


def emit_extraction_log(record: ExtractionLogRecord, path: Path | None) -> None:
    """Log a record and, when a path is configured, append it as one JSON line.

    Logging problems never interrupt an extraction.
    """
    line = record.model_dump_json()
    LOGGER.info(line)

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
    }
