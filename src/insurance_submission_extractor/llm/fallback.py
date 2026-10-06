from __future__ import annotations

from dataclasses import dataclass, field

from insurance_submission_extractor.llm.base import (
    ExtractionRunInfo,
    LLMClient,
    LLMClientError,
    TokenUsage,
)
from insurance_submission_extractor.llm.completeness import find_completeness_gaps
from insurance_submission_extractor.schemas import InsuranceSubmission


@dataclass
class _Tally:
    """Calls and usage of one request. Local to the request, so the client stays stateless."""

    calls: int = 0
    failed_calls: int = 0
    usage: list[TokenUsage] = field(default_factory=list)


def _attempt(
    client: LLMClient,
    submission_text: str,
    submission_id: str,
    tally: _Tally,
) -> InsuranceSubmission:
    tally.calls += 1

    try:
        with_usage = getattr(client, "extract_with_usage", None)

        if with_usage is None:
            return client.extract_submission(
                submission_text=submission_text, submission_id=submission_id
            )

        submission, usage = with_usage(submission_text=submission_text, submission_id=submission_id)
    except LLMClientError:
        tally.failed_calls += 1
        raise

    if usage is not None:
        tally.usage.append(usage)

    return submission


class FallbackLLMClient:
    """Primary provider with a reviewed fallback.

    The fallback runs when the primary provider fails, or when a deterministic
    check finds explicit source information that the primary left empty. Any
    fallback involvement or unresolved gap forces human review. Calls and token
    usage are reported per request, because a fallback adds cost. The client keeps
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
        tally = _Tally()

        try:
            primary_result = _attempt(self._primary, submission_text, submission_id, tally)
        except LLMClientError as error:
            return self._after_primary_failure(submission_text, submission_id, error, tally)

        gaps = find_completeness_gaps(submission_text, primary_result)

        if not gaps:
            return primary_result, self._primary_info(tally)

        try:
            fallback_result = _attempt(self._fallback, submission_text, submission_id, tally)
        except LLMClientError as error:
            return primary_result, self._primary_info(
                tally,
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
            return fallback_result, self._fallback_info(tally, notes)

        return primary_result, self._primary_info(
            tally,
            notes=[f"Fields possibly omitted, not resolved by fallback: {gaps}."],
            review_required=True,
        )

    def _primary_info(
        self,
        tally: _Tally,
        notes: list[str] | None = None,
        review_required: bool = False,
    ) -> ExtractionRunInfo:
        return ExtractionRunInfo(
            provider=self._primary.provider,
            model=self._primary.model,
            notes=notes or [],
            review_required=review_required,
            usage=tally.usage,
            calls=tally.calls,
            failed_calls=tally.failed_calls,
        )

    def _fallback_info(self, tally: _Tally, notes: list[str]) -> ExtractionRunInfo:
        return ExtractionRunInfo(
            provider=self._fallback.provider,
            model=self._fallback.model,
            notes=notes,
            review_required=True,
            usage=tally.usage,
            calls=tally.calls,
            failed_calls=tally.failed_calls,
        )

    def _after_primary_failure(
        self,
        submission_text: str,
        submission_id: str,
        primary_error: LLMClientError,
        tally: _Tally,
    ) -> tuple[InsuranceSubmission, ExtractionRunInfo]:
        try:
            fallback_result = _attempt(self._fallback, submission_text, submission_id, tally)
        except LLMClientError as fallback_error:
            raise LLMClientError(
                f"All providers failed. Primary: {primary_error}; fallback: {fallback_error}",
                calls=tally.calls,
                failed_calls=tally.failed_calls,
            ) from fallback_error

        notes = [
            f"Primary provider '{self._primary.provider}' failed ({primary_error}); "
            f"fallback provider '{self._fallback.provider}' used."
        ]
        gaps = find_completeness_gaps(submission_text, fallback_result)
        if gaps:
            notes.append(f"Fields possibly omitted: {gaps}.")

        return fallback_result, self._fallback_info(tally, notes)
