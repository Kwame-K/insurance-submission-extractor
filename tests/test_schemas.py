from datetime import UTC, datetime

import pytest
from pydantic import ValidationError

from insurance_submission_extractor.schemas import (
    ClaimRecord,
    ClaimsHistoryStatus,
    ClaimType,
    CoverageType,
    InsuranceSubmission,
    ProductLine,
)


def test_submission_accepts_valid_commercial_property_data() -> None:
    submission = InsuranceSubmission(
        submission_id="SUB-2026-0001",
        product_line=ProductLine.COMMERCIAL_PROPERTY,
        business_activity="Restaurant",
        location_city="Montreal",
        location_province="Quebec",
        building_construction_year=1998,
        employee_count=24,
        annual_revenue_cad=1_200_000,
        requested_coverages=[
            CoverageType.PROPERTY_DAMAGE,
            CoverageType.BUSINESS_INTERRUPTION,
        ],
        claims_history=[
            ClaimRecord(
                year=2023,
                claim_type=ClaimType.WATER_DAMAGE,
                amount_cad=18_000,
            )
        ],
    )

    assert submission.location_province == "QC"
    assert submission.annual_revenue_cad == 1_200_000
    assert len(submission.claims_history) == 1


def test_submission_rejects_negative_revenue() -> None:
    with pytest.raises(ValidationError):
        InsuranceSubmission(
            submission_id="SUB-2026-0002",
            annual_revenue_cad=-1,
        )


def test_submission_rejects_future_claim_year() -> None:
    future_year = datetime.now(UTC).year + 1

    with pytest.raises(ValidationError, match="Claim year cannot be in the future"):
        InsuranceSubmission(
            submission_id="SUB-2026-0003",
            claims_history=[
                ClaimRecord(
                    year=future_year,
                    claim_type=ClaimType.FIRE,
                    amount_cad=10_000,
                )
            ],
        )


def test_submission_marks_claims_as_reported_when_claims_exist() -> None:
    submission = InsuranceSubmission(
        submission_id="SUB-2026-0030",
        claims_history=[
            ClaimRecord(
                year=2024,
                claim_type=ClaimType.FIRE,
                amount_cad=10_000,
            )
        ],
    )

    assert submission.claims_history_status == ClaimsHistoryStatus.LOSSES_REPORTED


def test_submission_rejects_claims_when_no_losses_are_reported() -> None:
    with pytest.raises(
        ValidationError,
        match="Claims history cannot contain records",
    ):
        InsuranceSubmission(
            submission_id="SUB-2026-0031",
            claims_history_status=ClaimsHistoryStatus.NO_LOSSES_REPORTED,
            claims_history=[
                ClaimRecord(
                    year=2024,
                    claim_type=ClaimType.FIRE,
                    amount_cad=10_000,
                )
            ],
        )
