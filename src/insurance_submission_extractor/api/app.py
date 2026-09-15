"""FastAPI application exposing the versioned extraction HTTP contract."""

from __future__ import annotations

from typing import Protocol

from fastapi import FastAPI, HTTPException, Request, status

from insurance_submission_extractor.config import Settings
from insurance_submission_extractor.llm import LLMClientError, create_llm_client
from insurance_submission_extractor.schemas.integration import (
    ExtractionRequest,
    ExtractionStatus,
)
from insurance_submission_extractor.schemas.integration import (
    ExtractionResult as HttpExtractionResult,
)
from insurance_submission_extractor.services import SubmissionExtractor


class Extractor(Protocol):
    """Minimal interface required by the HTTP layer."""

    def extract(self, submission_text: str, submission_id: str) -> object:
        """Extract and validate one insurance submission."""


def get_extractor(request: Request) -> SubmissionExtractor:
    """Create the configured extractor lazily and cache it on the app instance."""
    extractor = getattr(request.app.state, "extractor", None)

    if extractor is None:
        settings = Settings()
        extractor = SubmissionExtractor(create_llm_client(settings))
        request.app.state.extractor = extractor

    return extractor


def to_http_result(
    source_id: str,
    extraction_result: object,
) -> HttpExtractionResult:
    """Adapt the internal domain result to the stable HTTP v1 contract."""
    submission = extraction_result.submission
    missing_fields = extraction_result.missing_fields

    extraction_status = ExtractionStatus.PARTIAL if missing_fields else ExtractionStatus.COMPLETE

    field_confidence: dict[str, float] = {}
    if extraction_result.extraction_confidence is not None:
        field_confidence["overall"] = extraction_result.extraction_confidence

    return HttpExtractionResult(
        source_id=source_id,
        extraction_status=extraction_status,
        submission_data=submission.model_dump(mode="json"),
        missing_fields=missing_fields,
        ambiguous_fields=[],
        field_confidence=field_confidence,
        source_references=[],
        data_quality_flags=[
            flag.model_dump(mode="json") for flag in extraction_result.data_quality_flags
        ],
        review_required=extraction_result.review_required,
        provider=extraction_result.provider,
        model=extraction_result.model,
        processed_at=extraction_result.processed_at,
        extraction_notes=extraction_result.extraction_notes,
    )


def create_app() -> FastAPI:
    """Create the extraction service API application."""
    app = FastAPI(
        title="Insurance Submission Extractor API",
        version="1.0.0",
        description=(
            "Extracts structured candidate data from unstructured commercial "
            "insurance submissions. It does not make underwriting decisions."
        ),
    )
    app.state.extractor = None

    @app.get("/health", tags=["Operations"])
    def health() -> dict[str, str]:
        """Return service availability without calling an LLM provider."""
        return {"status": "ok"}

    @app.post(
        "/v1/extract-submission",
        response_model=HttpExtractionResult,
        status_code=status.HTTP_200_OK,
        tags=["Extraction"],
    )
    def extract_submission(
        payload: ExtractionRequest,
        request: Request,
    ) -> HttpExtractionResult:
        """Extract candidate insurance data from a text-based source."""
        try:
            extractor = get_extractor(request)

            domain_result = extractor.extract(
                submission_text=payload.content,
                submission_id=payload.source_id,
            )

            return to_http_result(
                source_id=payload.source_id,
                extraction_result=domain_result,
            )
        except LLMClientError as error:
            raise HTTPException(
                status_code=status.HTTP_502_BAD_GATEWAY,
                detail={
                    "source_id": payload.source_id,
                    "error_code": "LLM_PROVIDER_ERROR",
                    "error_message": str(error),
                },
            ) from error

    return app


app = create_app()
