"""FastAPI application exposing the versioned extraction HTTP contract."""

from __future__ import annotations

from uuid import uuid4

from fastapi import FastAPI, HTTPException, Request, Response, status

from insurance_submission_extractor.config import Settings
from insurance_submission_extractor.llm import LLMClientError, create_llm_client
from insurance_submission_extractor.schemas.integration import (
    ExtractionRequest,
)
from insurance_submission_extractor.schemas.integration import (
    ExtractionResult as HttpExtractionResult,
)
from insurance_submission_extractor.services import SubmissionExtractor
from insurance_submission_extractor.services.http_adapter import to_http_result
from insurance_submission_extractor.services.telemetry import CORRELATION_ID

CORRELATION_ID_HEADER = "X-Correlation-ID"


def get_extractor(request: Request) -> SubmissionExtractor:
    """Create the configured extractor lazily and cache it on the app instance."""
    extractor = getattr(request.app.state, "extractor", None)

    if extractor is None:
        settings = Settings()
        extractor = SubmissionExtractor(
            create_llm_client(settings),
            extraction_log_path=settings.extraction_log_path,
            price_book=settings.price_book(),
        )
        request.app.state.extractor = extractor

    return extractor


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

    @app.middleware("http")
    async def add_correlation_id(
        request: Request,
        call_next: object,
    ) -> Response:
        """Propagate or generate a correlation identifier for every request."""
        correlation_id = request.headers.get(CORRELATION_ID_HEADER, str(uuid4()))
        request.state.correlation_id = correlation_id

        token = CORRELATION_ID.set(correlation_id)
        try:
            response = await call_next(request)
        finally:
            CORRELATION_ID.reset(token)
        response.headers[CORRELATION_ID_HEADER] = correlation_id

        return response

    @app.get("/health", tags=["Operations"])
    def health(request: Request) -> dict[str, str]:
        """Return service availability without calling an LLM provider."""
        return {
            "status": "ok",
            "correlation_id": request.state.correlation_id,
        }

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
                    "correlation_id": request.state.correlation_id,
                },
            ) from error

    return app


app = create_app()
