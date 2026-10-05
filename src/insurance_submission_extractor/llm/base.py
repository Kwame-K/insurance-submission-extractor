from __future__ import annotations

from dataclasses import dataclass, field
from typing import Protocol

from insurance_submission_extractor.schemas import InsuranceSubmission


class LLMClientError(RuntimeError):
    """Raised when an LLM provider cannot complete a request."""


@dataclass(frozen=True)
class ExtractionRunInfo:
    """Which provider produced an extraction, plus notes for reviewers."""

    provider: str
    model: str
    notes: list[str] = field(default_factory=list)
    review_required: bool = False


class LLMClient(Protocol):
    provider: str
    model: str

    def extract_submission(
        self,
        submission_text: str,
        submission_id: str,
    ) -> InsuranceSubmission:
        """Extract a structured insurance submission from unstructured text."""
