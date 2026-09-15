import pytest
from pydantic import ValidationError

from insurance_submission_extractor.schemas.integration import (
    ExtractionRequest,
    ExtractionResult,
    ExtractionStatus,
    SourceType,
)


def test_extraction_request_accepts_valid_text_intake() -> None:
    request = ExtractionRequest(
        source_id="SRC-BROKER-EMAIL-001",
        source_type=SourceType.BROKER_EMAIL,
        document_name="northwind-quote-request.txt",
        content="Please quote CAD 1M cyber coverage for Northwind Retail Inc.",
        language="en",
    )

    assert request.source_id == "SRC-BROKER-EMAIL-001"
    assert request.source_type is SourceType.BROKER_EMAIL
    assert request.language == "en"


def test_extraction_request_rejects_empty_content() -> None:
    with pytest.raises(ValidationError):
        ExtractionRequest(
            source_id="SRC-001",
            source_type=SourceType.FREE_TEXT,
            content="",
        )


def test_extraction_request_rejects_unknown_fields() -> None:
    with pytest.raises(ValidationError):
        ExtractionRequest(
            source_id="SRC-001",
            source_type=SourceType.FREE_TEXT,
            content="Please quote cyber coverage.",
            unexpected_field="must fail",
        )


def test_partial_result_preserves_missing_fields_and_provenance() -> None:
    result = ExtractionResult(
        source_id="SRC-001",
        extraction_status=ExtractionStatus.PARTIAL,
        submission_data={
            "applicant_name": "Northwind Retail Inc.",
            "annual_revenue_cad": 8_000_000,
        },
        missing_fields=["requested_retention_cad"],
        ambiguous_fields=[],
        field_confidence={
            "applicant_name": 0.99,
            "annual_revenue_cad": 0.94,
        },
        source_references=[
            {
                "field_name": "annual_revenue_cad",
                "source_excerpt": "Annual revenue: CAD 8M",
                "page_number": 1,
            }
        ],
    )

    assert result.extraction_status is ExtractionStatus.PARTIAL
    assert result.submission_data["annual_revenue_cad"] == 8_000_000
    assert result.missing_fields == ["requested_retention_cad"]
    assert result.source_references[0].page_number == 1


def test_failed_result_can_expose_a_safe_error_code() -> None:
    result = ExtractionResult(
        source_id="SRC-001",
        extraction_status=ExtractionStatus.FAILED,
        error_code="EXTRACTION_PROVIDER_UNAVAILABLE",
        error_message="The extraction provider did not respond before the timeout.",
    )

    assert result.submission_data == {}
    assert result.error_code == "EXTRACTION_PROVIDER_UNAVAILABLE"


def test_result_rejects_confidence_above_one() -> None:
    with pytest.raises(ValidationError):
        ExtractionResult(
            source_id="SRC-001",
            extraction_status=ExtractionStatus.COMPLETE,
            field_confidence={"applicant_name": 1.01},
        )


def test_result_rejects_confidence_below_zero() -> None:
    with pytest.raises(ValidationError):
        ExtractionResult(
            source_id="SRC-001",
            extraction_status=ExtractionStatus.COMPLETE,
            field_confidence={"applicant_name": -0.01},
        )


def test_source_reference_rejects_page_zero() -> None:
    with pytest.raises(ValidationError):
        ExtractionResult(
            source_id="SRC-001",
            extraction_status=ExtractionStatus.COMPLETE,
            source_references=[
                {
                    "field_name": "annual_revenue_cad",
                    "page_number": 0,
                }
            ],
        )
