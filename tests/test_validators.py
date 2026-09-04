from insurance_submission_extractor.schemas import (
    ClaimRecord,
    ClaimType,
    CoverageType,
    InsuranceSubmission,
    ProductLine,
)
from insurance_submission_extractor.services.validators import (
    get_missing_fields,
    validate_submission,
)


def test_get_missing_fields_for_incomplete_property_submission() -> None:
    submission = InsuranceSubmission(
        submission_id="SUB-2026-0010",
        product_line=ProductLine.COMMERCIAL_PROPERTY,
        business_activity="Restaurant",
        location_city="Montreal",
        location_province="QC",
        annual_revenue_cad=900_000,
        requested_coverages=[CoverageType.PROPERTY_DAMAGE],
    )

    missing_fields = get_missing_fields(submission)

    assert missing_fields == [
        "postal_code",
        "building_construction_year",
        "occupancy_type",
    ]


def test_validation_requires_review_when_required_fields_are_missing() -> None:
    submission = InsuranceSubmission(
        submission_id="SUB-2026-0011",
        product_line=ProductLine.COMMERCIAL_PROPERTY,
        business_activity="Restaurant",
    )

    report = validate_submission(submission)

    assert report.review_required is True
    assert "location_city" in report.missing_fields
    assert "annual_revenue_cad" in report.missing_fields
    assert "building_construction_year" in report.missing_fields


def test_validation_detects_building_year_after_claim() -> None:
    submission = InsuranceSubmission(
        submission_id="SUB-2026-0012",
        product_line=ProductLine.COMMERCIAL_PROPERTY,
        business_activity="Restaurant",
        location_city="Montreal",
        location_province="QC",
        postal_code="H2X 1Y4",
        building_construction_year=2025,
        occupancy_type="Restaurant",
        employee_count=12,
        annual_revenue_cad=750_000,
        requested_coverages=[CoverageType.PROPERTY_DAMAGE],
        claims_history=[
            ClaimRecord(
                year=2023,
                claim_type=ClaimType.WATER_DAMAGE,
                amount_cad=15_000,
            )
        ],
    )

    report = validate_submission(submission)

    assert report.review_required is False
    assert len(report.data_quality_flags) == 1
    assert report.data_quality_flags[0].code == "BUILDING_YEAR_AFTER_CLAIM"


def test_validation_detects_duplicate_claims() -> None:
    duplicate_claim = ClaimRecord(
        year=2024,
        claim_type=ClaimType.FIRE,
        amount_cad=25_000,
    )

    submission = InsuranceSubmission(
        submission_id="SUB-2026-0013",
        product_line=ProductLine.COMMERCIAL_PROPERTY,
        business_activity="Warehouse",
        location_city="Laval",
        location_province="QC",
        postal_code="H7N 1A1",
        building_construction_year=2001,
        occupancy_type="Warehouse",
        employee_count=18,
        annual_revenue_cad=1_500_000,
        requested_coverages=[CoverageType.PROPERTY_DAMAGE],
        claims_history=[duplicate_claim, duplicate_claim],
    )

    report = validate_submission(submission)

    assert any(flag.code == "POSSIBLE_DUPLICATE_CLAIMS" for flag in report.data_quality_flags)
