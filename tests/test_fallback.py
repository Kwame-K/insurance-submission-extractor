import pytest

from insurance_submission_extractor.config import LLMProvider, Settings
from insurance_submission_extractor.llm import (
    FallbackLLMClient,
    LLMClientError,
    factory,
    find_completeness_gaps,
)
from insurance_submission_extractor.schemas import CoverageType, InsuranceSubmission
from insurance_submission_extractor.services import SubmissionExtractor

TEXT = (
    "We want a quote for our restaurant in Montreal, Quebec H2X 1Y4. "
    "The building was constructed in 1998. We have 24 employees. "
    "Annual revenue is approximately CAD 1,200,000. "
    "We are seeking commercial property and business interruption coverage."
)

FULL = {
    "annual_revenue_cad": 1_200_000.0,
    "employee_count": 24,
    "building_construction_year": 1998,
    "postal_code": "H2X 1Y4",
    "requested_coverages": [CoverageType.PROPERTY_DAMAGE, CoverageType.BUSINESS_INTERRUPTION],
}


class FakeClient:
    def __init__(self, provider: str, **fields: object) -> None:
        self.provider = provider
        self.model = f"{provider}-model"
        self.fields = fields
        self.calls = 0

    def extract_submission(self, submission_text: str, submission_id: str) -> InsuranceSubmission:
        self.calls += 1
        if self.fields.get("error"):
            raise LLMClientError(str(self.fields["error"]))
        data = {k: v for k, v in self.fields.items() if k != "error"}
        return InsuranceSubmission(submission_id=submission_id, **data)


def run(primary: FakeClient, fallback: FakeClient):
    client = FallbackLLMClient(primary=primary, fallback=fallback)
    return client.extract_with_report(TEXT, "S1")


def test_complete_primary_output_does_not_call_fallback() -> None:
    primary, fallback = FakeClient("gemini", **FULL), FakeClient("groq", **FULL)
    _, info = run(primary, fallback)

    assert (info.provider, info.review_required, info.notes) == ("gemini", False, [])
    assert fallback.calls == 0


def test_primary_failure_uses_fallback_and_requires_review() -> None:
    _, info = run(FakeClient("gemini", error="quota"), FakeClient("groq", **FULL))

    assert info.provider == "groq"
    assert info.review_required is True
    assert "quota" in info.notes[0]


def test_gap_in_primary_triggers_better_fallback() -> None:
    partial = {**FULL, "annual_revenue_cad": None}
    submission, info = run(FakeClient("gemini", **partial), FakeClient("groq", **FULL))

    assert submission.annual_revenue_cad == 1_200_000.0
    assert info.provider == "groq"
    assert info.review_required is True
    assert "annual_revenue_cad" in info.notes[0]


def test_fallback_not_better_keeps_primary_but_flags_review() -> None:
    partial = {**FULL, "annual_revenue_cad": None}
    _, info = run(FakeClient("gemini", **partial), FakeClient("groq", **partial))

    assert info.provider == "gemini"
    assert info.review_required is True
    assert "annual_revenue_cad" in info.notes[0]


def test_gap_with_unavailable_fallback_keeps_primary_with_review() -> None:
    partial = {**FULL, "employee_count": None}
    _, info = run(FakeClient("gemini", **partial), FakeClient("groq", error="down"))

    assert info.provider == "gemini"
    assert info.review_required is True
    assert "down" in info.notes[0]


def test_both_providers_failing_raises() -> None:
    with pytest.raises(LLMClientError, match="All providers failed"):
        run(FakeClient("gemini", error="a"), FakeClient("groq", error="b"))


def test_product_wording_and_distractors_are_not_gaps() -> None:
    text = (
        "Quote for commercial property insurance for our restaurant. "
        "The company has been in business since 1987. Call 514-555-0187."
    )
    submission = InsuranceSubmission(submission_id="S")

    assert find_completeness_gaps(text, submission) == []


def test_explicit_coverage_wording_is_a_gap_when_missing() -> None:
    submission = InsuranceSubmission(
        submission_id="S",
        requested_coverages=[CoverageType.BUSINESS_INTERRUPTION],
    )

    assert "requested_coverages" in find_completeness_gaps(TEXT, submission)


def test_extractor_surfaces_fallback_provider_notes_and_review() -> None:
    partial = {**FULL, "annual_revenue_cad": None}
    client = FallbackLLMClient(FakeClient("gemini", **partial), FakeClient("groq", **FULL))
    result = SubmissionExtractor(client).extract(TEXT, "S1")

    assert result.provider == "groq"
    assert result.review_required is True
    assert result.extraction_notes


def test_factory_builds_fallback_client_only_when_configured(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(factory, "GeminiClient", lambda settings: FakeClient("gemini"))
    monkeypatch.setattr(factory, "GroqClient", lambda settings: FakeClient("groq"))

    single = factory.create_llm_client(Settings(llm_provider=LLMProvider.GEMINI))
    combined = factory.create_llm_client(
        Settings(
            llm_provider=LLMProvider.GEMINI,
            llm_fallback_provider=LLMProvider.GROQ,
        )
    )
    same = factory.create_llm_client(
        Settings(
            llm_provider=LLMProvider.GEMINI,
            llm_fallback_provider=LLMProvider.GEMINI,
        )
    )

    assert single.provider == "gemini"
    assert isinstance(combined, FallbackLLMClient)
    assert combined.name == "gemini+groq"
    assert same.provider == "gemini"
    assert not isinstance(same, FallbackLLMClient)


def test_fallback_provider_is_read_from_environment(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("LLM_FALLBACK_PROVIDER", "groq")

    assert Settings().llm_fallback_provider == LLMProvider.GROQ
