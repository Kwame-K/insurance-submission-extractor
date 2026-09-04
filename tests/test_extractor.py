from insurance_submission_extractor.schemas import (
    CoverageType,
    InsuranceSubmission,
    ProductLine,
)
from insurance_submission_extractor.services import SubmissionExtractor


class FakeLLMClient:
    provider = "fake"
    model = "fake-model"

    def extract_submission(
        self,
        submission_text: str,
        submission_id: str,
    ) -> InsuranceSubmission:
        return InsuranceSubmission(
            submission_id=submission_id,
            product_line=ProductLine.COMMERCIAL_PROPERTY,
            business_activity="Restaurant",
            location_city="Montreal",
            location_province="QC",
            postal_code="H2X 1Y4",
            building_construction_year=1998,
            occupancy_type="Restaurant",
            employee_count=24,
            annual_revenue_cad=1_200_000,
            requested_coverages=[
                CoverageType.PROPERTY_DAMAGE,
                CoverageType.BUSINESS_INTERRUPTION,
            ],
        )


def test_extractor_returns_validated_result() -> None:
    extractor = SubmissionExtractor(
        llm_client=FakeLLMClient(),
    )

    result = extractor.extract(
        submission_text="Synthetic submission text.",
        submission_id="SUB-2026-0021",
    )

    assert result.submission.submission_id == "SUB-2026-0021"
    assert result.provider == "fake"
    assert result.model == "fake-model"
    assert result.missing_fields == []
    assert result.extraction_confidence is None
    assert result.review_required is False


def test_extractor_requires_review_for_incomplete_submission() -> None:
    class FakeIncompleteLLMClient:
        provider = "fake"
        model = "fake-model"

        def extract_submission(
            self,
            submission_text: str,
            submission_id: str,
        ) -> InsuranceSubmission:
            return InsuranceSubmission(
                submission_id=submission_id,
                product_line=ProductLine.COMMERCIAL_PROPERTY,
                business_activity="Retail store",
                location_city="Montreal",
                location_province="QC",
                annual_revenue_cad=450_000,
            )

    extractor = SubmissionExtractor(
        llm_client=FakeIncompleteLLMClient(),
    )

    result = extractor.extract(
        submission_text="Synthetic incomplete submission.",
        submission_id="SUB-2026-0040",
    )

    assert result.review_required is True
    assert "postal_code" in result.missing_fields
    assert "building_construction_year" in result.missing_fields
    assert "occupancy_type" not in result.missing_fields
    assert result.submission.occupancy_type == "retail store"
