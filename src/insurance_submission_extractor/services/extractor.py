from __future__ import annotations

from insurance_submission_extractor.llm import LLMClient
from insurance_submission_extractor.schemas import ExtractionResult
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
        submission = self._llm_client.extract_submission(
            submission_text=submission_text,
            submission_id=submission_id,
        )
        submission = normalize_submission(submission)

        validation_report = validate_submission(submission)

        return ExtractionResult(
            submission=submission,
            missing_fields=validation_report.missing_fields,
            data_quality_flags=validation_report.data_quality_flags,
            extraction_confidence=None,
            extraction_notes=[],
            provider=self._llm_client.provider,
            model=self._llm_client.model,
            review_required=validation_report.review_required,
        )
