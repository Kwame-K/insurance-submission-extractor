import json
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from insurance_submission_extractor.api.app import create_app
from insurance_submission_extractor.config import Settings
from insurance_submission_extractor.llm import FallbackLLMClient, LLMClientError
from insurance_submission_extractor.schemas import (
    CoverageType,
    InsuranceSubmission,
    ProductLine,
)
from insurance_submission_extractor.services import SubmissionExtractor
from insurance_submission_extractor.services.telemetry import (
    read_records,
    summarize_records,
)

TEXT = (
    "Le Jardin Bistro is a restaurant in Montreal, QC H2X 1Y4. Built in 1998. "
    "It has 24 employees and annual revenue of CAD 1,200,000. "
    "We are seeking commercial property and business interruption coverage."
)


class FakeClient:
    def __init__(self, provider: str, fail: bool = False) -> None:
        self.provider = provider
        self.model = f"{provider}-model"
        self.fail = fail

    def extract_submission(self, submission_text: str, submission_id: str) -> InsuranceSubmission:
        if self.fail:
            raise LLMClientError("Provider is unavailable.")
        return InsuranceSubmission(
            submission_id=submission_id,
            product_line=ProductLine.COMMERCIAL_PROPERTY,
            insured_name="Le Jardin Bistro",
            business_activity="restaurant",
            location_city="Montreal",
            location_province="QC",
            postal_code="H2X 1Y4",
            building_construction_year=1998,
            employee_count=24,
            annual_revenue_cad=1_200_000,
            requested_coverages=[
                CoverageType.PROPERTY_DAMAGE,
                CoverageType.BUSINESS_INTERRUPTION,
            ],
        )


def lines(path: Path) -> list[dict]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines()]


def test_successful_extraction_writes_one_content_free_record(tmp_path: Path) -> None:
    log = tmp_path / "logs" / "extractions.jsonl"
    SubmissionExtractor(FakeClient("gemini"), log).extract(TEXT, "SRC-1")

    (record,) = lines(log)

    assert record["status"] == "ok"
    assert record["submission_id"] == "SRC-1"
    assert record["provider"] == "gemini"
    assert record["fallback_used"] is False
    assert record["duration_ms"] >= 0
    contents = log.read_text(encoding="utf-8")
    for private in ("Montreal", "H2X", "Jardin", "1,200,000", "business interruption"):
        assert private not in contents


def test_fallback_use_is_recorded(tmp_path: Path) -> None:
    log = tmp_path / "extractions.jsonl"
    client = FallbackLLMClient(FakeClient("gemini", fail=True), FakeClient("groq"))
    SubmissionExtractor(client, log).extract(TEXT, "SRC-2")

    (record,) = lines(log)

    assert record["provider"] == "groq"
    assert record["fallback_used"] is True
    assert record["review_required"] is True


def test_failure_is_logged_and_reraised(tmp_path: Path) -> None:
    log = tmp_path / "extractions.jsonl"

    with pytest.raises(LLMClientError):
        SubmissionExtractor(FakeClient("gemini", fail=True), log).extract(TEXT, "SRC-3")

    (record,) = lines(log)

    assert record["status"] == "error"
    assert record["error_type"] == "LLMClientError"
    assert "Provider is unavailable" not in log.read_text(encoding="utf-8")


def test_unwritable_log_path_does_not_break_extraction(tmp_path: Path) -> None:
    result = SubmissionExtractor(FakeClient("gemini"), tmp_path).extract(TEXT, "SRC-4")

    assert result.submission.submission_id == "SRC-4"


def test_api_correlation_id_is_logged(tmp_path: Path) -> None:
    log = tmp_path / "extractions.jsonl"
    app = create_app()
    app.state.extractor = SubmissionExtractor(FakeClient("gemini"), log)
    payload = {
        "source_id": "SRC-5",
        "source_type": "BROKER_EMAIL",
        "content": TEXT,
        "language": "en",
    }

    response = TestClient(app).post(
        "/v1/extract-submission", json=payload, headers={"X-Correlation-ID": "corr-123"}
    )

    assert response.status_code == 200
    assert lines(log)[0]["correlation_id"] == "corr-123"


def test_summary_computes_rates_and_latency() -> None:
    base = {"event": "extraction", "model": "m", "submission_id": "S"}
    records = [
        {
            **base,
            "status": "ok",
            "provider": "gemini",
            "duration_ms": 100,
            "review_required": False,
            "unsupported_fields": [],
        },
        {
            **base,
            "status": "ok",
            "provider": "gemini",
            "duration_ms": 200,
            "review_required": False,
            "unsupported_fields": [],
        },
        {
            **base,
            "status": "ok",
            "provider": "groq",
            "duration_ms": 300,
            "fallback_used": True,
            "review_required": True,
            "unsupported_fields": ["location_province"],
        },
        {**base, "status": "error", "provider": "gemini", "duration_ms": 400},
    ]
    summary = summarize_records(records)

    assert summary["total_extractions"] == 4
    assert summary["error_rate"] == 0.25
    assert summary["fallback_rate"] == pytest.approx(0.3333, abs=1e-4)
    assert summary["review_rate"] == pytest.approx(0.3333, abs=1e-4)
    assert summary["latency_ms"] == {"p50": 200.0, "p95": 400.0, "max": 400.0}
    assert summary["unsupported_by_field"] == {"location_province": 1}
    assert summary["successful_by_provider"]["groq"]["count"] == 1


def test_read_records_skips_malformed_lines(tmp_path: Path) -> None:
    path = tmp_path / "log.jsonl"
    path.write_text(
        'not json\n{"event": "other"}\n{"event": "extraction", "status": "ok"}\n', encoding="utf-8"
    )

    assert len(read_records(path)) == 1


def test_log_path_is_read_from_environment(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("EXTRACTION_LOG_PATH", "logs/extractions.jsonl")

    assert Settings(_env_file=None).extraction_log_path == Path("logs/extractions.jsonl")
