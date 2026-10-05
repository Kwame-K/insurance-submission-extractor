"""Adapter from the extractor domain result to the public integration contract."""

from __future__ import annotations

from insurance_submission_extractor.schemas.integration import (
    ExtractionResult as HttpExtractionResult,
)
from insurance_submission_extractor.schemas.integration import (
    ExtractionStatus,
    SourceReference,
)


def to_http_result(source_id: str, extraction_result: object) -> HttpExtractionResult:
    """Map a domain extraction result to the stable v1 response schema."""
    submission = extraction_result.submission
    missing_fields = extraction_result.missing_fields
    field_confidence: dict[str, float] = {}
    if extraction_result.extraction_confidence is not None:
        field_confidence["overall"] = extraction_result.extraction_confidence

    return HttpExtractionResult(
        source_id=source_id,
        extraction_status=(
            ExtractionStatus.PARTIAL if missing_fields else ExtractionStatus.COMPLETE
        ),
        submission_data=submission.model_dump(mode="json"),
        missing_fields=missing_fields,
        ambiguous_fields=list(extraction_result.unsupported_fields),
        field_confidence=field_confidence,
        source_references=[
            SourceReference(
                field_name=reference.field_name,
                source_excerpt=reference.source_excerpt,
            )
            for reference in extraction_result.source_references
        ],
        data_quality_flags=[
            flag.model_dump(mode="json") for flag in extraction_result.data_quality_flags
        ],
        review_required=extraction_result.review_required,
        provider=extraction_result.provider,
        model=extraction_result.model,
        processed_at=extraction_result.processed_at,
        extraction_notes=extraction_result.extraction_notes,
    )
