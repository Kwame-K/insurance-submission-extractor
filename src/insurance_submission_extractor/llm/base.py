from __future__ import annotations

from dataclasses import dataclass, field
from typing import Protocol

from insurance_submission_extractor.schemas import InsuranceSubmission


class LLMClientError(RuntimeError):
    """Raised when an LLM provider cannot complete a request.

    ``calls`` and ``failed_calls`` count the provider calls made before giving up.
    A single client makes one call; a fallback client may have made two.
    """

    def __init__(self, message: str = "", *, calls: int = 1, failed_calls: int = 1) -> None:
        super().__init__(message)
        self.calls = calls
        self.failed_calls = failed_calls


@dataclass(frozen=True)
class TokenUsage:
    """Billed token counts for one provider call. Output includes reasoning tokens."""

    provider: str
    model: str
    input_tokens: int
    output_tokens: int

    @property
    def total_tokens(self) -> int:
        return self.input_tokens + self.output_tokens


@dataclass(frozen=True)
class ExtractionRunInfo:
    """Which provider produced an extraction, plus notes for reviewers."""

    provider: str
    model: str
    notes: list[str] = field(default_factory=list)
    review_required: bool = False
    usage: list[TokenUsage] = field(default_factory=list)
    calls: int = 1
    failed_calls: int = 0


class LLMClient(Protocol):
    provider: str
    model: str

    def extract_submission(
        self,
        submission_text: str,
        submission_id: str,
    ) -> InsuranceSubmission:
        """Extract a structured insurance submission from unstructured text."""
