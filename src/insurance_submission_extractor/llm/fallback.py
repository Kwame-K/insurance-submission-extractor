from __future__ import annotations

from insurance_submission_extractor.llm.base import ExtractionRunInfo, LLMClient, LLMClientError
from insurance_submission_extractor.llm.completeness import find_completeness_gaps
from insurance_submission_extractor.schemas import InsuranceSubmission


class FallbackLLMClient:
    """Primary provider with a reviewed fallback.

    The fallback runs when the primary provider fails, or when a deterministic
    check finds explicit source information that the primary left empty. Any
    fallback involvement or unresolved gap forces human review. The client keeps
    no per-request state, so it is safe to share across concurrent requests.
    """

    def __init__(self, primary: LLMClient, fallback: LLMClient) -> None:
        self._primary = primary
        self._fallback = fallback
        self.provider = primary.provider
        self.model = primary.model

    @property
    def name(self) -> str:
        return f"{self._primary.provider}+{self._fallback.provider}"

    def extract_submission(
        self,
        submission_text: str,
        submission_id: str,
    ) -> InsuranceSubmission:
        submission, _ = self.extract_with_report(submission_text, submission_id)

        return submission

    def extract_with_report(
        self,
        submission_text: str,
        submission_id: str,
    ) -> tuple[InsuranceSubmission, ExtractionRunInfo]:
        primary_info = ExtractionRunInfo(
            provider=self._primary.provider,
            model=self._primary.model,
        )

        try:
            primary_result = self._primary.extract_submission(
                submission_text=submission_text,
                submission_id=submission_id,
            )
        except LLMClientError as error:
            return self._after_primary_failure(submission_text, submission_id, error)

        gaps = find_completeness_gaps(submission_text, primary_result)

        if not gaps:
            return primary_result, primary_info

        try:
            fallback_result = self._fallback.extract_submission(
                submission_text=submission_text,
                submission_id=submission_id,
            )
        except LLMClientError as error:
            return primary_result, ExtractionRunInfo(
                provider=primary_info.provider,
                model=primary_info.model,
                notes=[
                    f"Primary output may omit explicit fields {gaps}; "
                    f"fallback provider unavailable: {error}"
                ],
                review_required=True,
            )

        fallback_gaps = find_completeness_gaps(submission_text, fallback_result)

        if len(fallback_gaps) < len(gaps):
            notes = [
                f"Fallback provider '{self._fallback.provider}' used because the primary "
                f"provider '{self._primary.provider}' omitted explicit fields {gaps}."
            ]
            if fallback_gaps:
                notes.append(f"Fields still possibly omitted: {fallback_gaps}.")
            return fallback_result, ExtractionRunInfo(
                provider=self._fallback.provider,
                model=self._fallback.model,
                notes=notes,
                review_required=True,
            )

        return primary_result, ExtractionRunInfo(
            provider=primary_info.provider,
            model=primary_info.model,
            notes=[f"Fields possibly omitted, not resolved by fallback: {gaps}."],
            review_required=True,
        )

    def _after_primary_failure(
        self,
        submission_text: str,
        submission_id: str,
        primary_error: LLMClientError,
    ) -> tuple[InsuranceSubmission, ExtractionRunInfo]:
        try:
            fallback_result = self._fallback.extract_submission(
                submission_text=submission_text,
                submission_id=submission_id,
            )
        except LLMClientError as fallback_error:
            raise LLMClientError(
                f"All providers failed. Primary: {primary_error}; fallback: {fallback_error}"
            ) from fallback_error

        notes = [
            f"Primary provider '{self._primary.provider}' failed ({primary_error}); "
            f"fallback provider '{self._fallback.provider}' used."
        ]
        gaps = find_completeness_gaps(submission_text, fallback_result)
        if gaps:
            notes.append(f"Fields possibly omitted: {gaps}.")

        return fallback_result, ExtractionRunInfo(
            provider=self._fallback.provider,
            model=self._fallback.model,
            notes=notes,
            review_required=True,
        )
