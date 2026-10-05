from __future__ import annotations

from insurance_submission_extractor.llm import ExtractionRunInfo, LLMClient
from insurance_submission_extractor.schemas import (
    DataQualityFlag,
    DataQualitySeverity,
    ExtractionResult,
)
from insurance_submission_extractor.services.evidence import find_field_evidence
from insurance_submission_extractor.services.normalizers import (
    normalize_submission,
)
from insurance_submission_extractor.services.validators import validate_submission


class SubmissionExtractor:
    def __init__(self, llm_client: LLMClient) -> None:
        self._llm_client = llm_client

    def extract(
        self,
        submission_text: str,
        submission_id: str,
    ) -> ExtractionResult:
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

        return ExtractionResult(
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
