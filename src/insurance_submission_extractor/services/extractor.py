from __future__ import annotations

import time
from pathlib import Path

from insurance_submission_extractor.llm import ExtractionRunInfo, LLMClient
from insurance_submission_extractor.pricing import PriceBook
from insurance_submission_extractor.schemas import (
    DataQualityFlag,
    DataQualitySeverity,
    ExtractionResult,
)
from insurance_submission_extractor.services.evidence import find_field_evidence
from insurance_submission_extractor.services.normalizers import (
    normalize_submission,
)
from insurance_submission_extractor.services.telemetry import (
    CORRELATION_ID,
    AttemptUsage,
    ExtractionLogRecord,
    emit_extraction_log,
)
from insurance_submission_extractor.services.validators import validate_submission


class SubmissionExtractor:
    def __init__(
        self,
        llm_client: LLMClient,
        extraction_log_path: Path | None = None,
        price_book: PriceBook | None = None,
    ) -> None:
        self._llm_client = llm_client
        self._extraction_log_path = extraction_log_path
        self._price_book = price_book or PriceBook()

    def extract(
        self,
        submission_text: str,
        submission_id: str,
    ) -> ExtractionResult:
        started = time.perf_counter()

        try:
            result, run_info = self._extract(submission_text, submission_id)
        except Exception as error:
            emit_extraction_log(
                ExtractionLogRecord(
                    submission_id=submission_id,
                    correlation_id=CORRELATION_ID.get(),
                    status="error",
                    provider=getattr(self._llm_client, "name", self._llm_client.provider),
                    model=self._llm_client.model,
                    duration_ms=self._elapsed_ms(started),
                    error_type=type(error).__name__,
                    llm_calls=getattr(error, "calls", 1),
                    failed_llm_calls=getattr(error, "failed_calls", 1),
                ),
                self._extraction_log_path,
            )
            raise

        usage = run_info.usage
        input_tokens = sum(u.input_tokens for u in usage) if usage else None
        output_tokens = sum(u.output_tokens for u in usage) if usage else None

        emit_extraction_log(
            ExtractionLogRecord(
                submission_id=submission_id,
                correlation_id=CORRELATION_ID.get(),
                status="ok",
                provider=result.provider,
                model=result.model,
                duration_ms=self._elapsed_ms(started),
                fallback_used=result.provider != self._llm_client.provider,
                review_required=result.review_required,
                missing_field_count=len(result.missing_fields),
                unsupported_fields=list(result.unsupported_fields),
                attempts=[
                    AttemptUsage(
                        provider=usage.provider,
                        model=usage.model,
                        input_tokens=usage.input_tokens,
                        output_tokens=usage.output_tokens,
                    )
                    for usage in run_info.usage
                ],
                input_tokens=input_tokens,
                output_tokens=output_tokens,
                cost_usd=self._price_book.cost_usd(run_info.usage),
                llm_calls=run_info.calls,
                failed_llm_calls=run_info.failed_calls,
            ),
            self._extraction_log_path,
        )

        return result

    @staticmethod
    def _elapsed_ms(started: float) -> float:
        return round((time.perf_counter() - started) * 1000, 1)

    def _extract(
        self,
        submission_text: str,
        submission_id: str,
    ) -> tuple[ExtractionResult, ExtractionRunInfo]:
        run_info = ExtractionRunInfo(
            provider=self._llm_client.provider,
            model=self._llm_client.model,
        )
        extract_with_report = getattr(self._llm_client, "extract_with_report", None)

        if extract_with_report is not None:
            submission, run_info = extract_with_report(
                submission_text=submission_text,
                submission_id=submission_id,
            )
        elif getattr(self._llm_client, "extract_with_usage", None) is not None:
            submission, usage = self._llm_client.extract_with_usage(
                submission_text=submission_text,
                submission_id=submission_id,
            )
            run_info = ExtractionRunInfo(
                provider=run_info.provider,
                model=run_info.model,
                usage=[usage] if usage is not None else [],
            )
        else:
            submission = self._llm_client.extract_submission(
                submission_text=submission_text,
                submission_id=submission_id,
            )

        submission = normalize_submission(submission)

        validation_report = validate_submission(submission)
        source_references, unsupported_fields = find_field_evidence(submission_text, submission)
        evidence_flags = [
            DataQualityFlag(
                field=field_name,
                severity=DataQualitySeverity.WARNING,
                code="VALUE_NOT_FOUND_IN_SOURCE",
                message=(
                    f"No passage in the source text supports the extracted {field_name}; "
                    "verify it before use."
                ),
            )
            for field_name in unsupported_fields
        ]

        result = ExtractionResult(
            submission=submission,
            missing_fields=validation_report.missing_fields,
            data_quality_flags=[*validation_report.data_quality_flags, *evidence_flags],
            extraction_confidence=None,
            extraction_notes=list(run_info.notes),
            source_references=source_references,
            unsupported_fields=unsupported_fields,
            provider=run_info.provider,
            model=run_info.model,
            review_required=(
                validation_report.review_required
                or run_info.review_required
                or bool(unsupported_fields)
            ),
        )

        return result, run_info
