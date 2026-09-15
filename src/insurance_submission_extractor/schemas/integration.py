"""Versioned HTTP contract used by downstream underwriting services."""

from __future__ import annotations

from datetime import datetime
from enum import StrEnum
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, field_validator


class ExtractionStatus(StrEnum):
    """Outcome of one extraction attempt."""

    COMPLETE = "COMPLETE"
    PARTIAL = "PARTIAL"
    FAILED = "FAILED"


class SourceType(StrEnum):
    """Supported text-based intake sources for contract version 1."""

    BROKER_EMAIL = "BROKER_EMAIL"
    PDF_TEXT = "PDF_TEXT"
    FREE_TEXT = "FREE_TEXT"
    FORM = "FORM"


class ExtractionRequest(BaseModel):
    """
    Text-only intake payload.

    Binary uploads are intentionally out of scope for v1. A PDF must first be
    converted to text by the caller or by a future dedicated ingestion layer.
    """

    model_config = ConfigDict(
        extra="forbid",
        str_strip_whitespace=True,
    )

    source_id: str = Field(
        min_length=1,
        max_length=128,
        examples=["SRC-BROKER-EMAIL-001"],
    )
    source_type: SourceType
    document_name: str | None = Field(
        default=None,
        max_length=512,
        examples=["northwind-quote-request.txt"],
    )
    content: str = Field(
        min_length=1,
        description="Raw broker email, form text, or text extracted from a PDF.",
    )
    language: str = Field(
        default="en",
        min_length=2,
        max_length=16,
        examples=["en", "fr"],
    )


class SourceReference(BaseModel):
    """
    Evidence supporting one candidate extracted field.

    `source_excerpt` is returned to help a reviewer verify the extraction.
    It should not automatically be persisted in a long-term audit payload.
    """

    model_config = ConfigDict(
        extra="forbid",
        str_strip_whitespace=True,
    )

    field_name: str = Field(
        min_length=1,
        examples=["annual_revenue_cad"],
    )
    source_excerpt: str | None = Field(
        default=None,
        examples=["Annual revenue: CAD 8M"],
    )
    page_number: int | None = Field(
        default=None,
        ge=1,
        examples=[1],
    )


class ExtractionResult(BaseModel):
    """
    Stable response contract returned by the extraction service.

    `submission_data` is only candidate data. A downstream consumer must
    validate it with its own canonical domain model before underwriting.
    """

    model_config = ConfigDict(extra="forbid")

    source_id: str = Field(min_length=1, max_length=128)
    extraction_status: ExtractionStatus

    submission_data: dict[str, Any] = Field(default_factory=dict)
    missing_fields: list[str] = Field(default_factory=list)
    ambiguous_fields: list[str] = Field(default_factory=list)

    field_confidence: dict[str, float] = Field(default_factory=dict)
    source_references: list[SourceReference] = Field(default_factory=list)

    data_quality_flags: list[dict[str, Any]] = Field(default_factory=list)
    review_required: bool = False

    provider: str | None = None
    model: str | None = None
    processed_at: datetime | None = None

    extraction_notes: list[str] = Field(default_factory=list)

    error_code: str | None = None
    error_message: str | None = None

    @field_validator("field_confidence")
    @classmethod
    def validate_confidence_values(
        cls,
        field_confidence: dict[str, float],
    ) -> dict[str, float]:
        for field_name, confidence in field_confidence.items():
            if not 0.0 <= confidence <= 1.0:
                raise ValueError(f"Confidence for '{field_name}' must be between 0.0 and 1.0.")

        return field_confidence
