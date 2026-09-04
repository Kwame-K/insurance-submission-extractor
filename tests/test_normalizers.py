from insurance_submission_extractor.schemas import (
    InsuranceSubmission,
    ProductLine,
)
from insurance_submission_extractor.services.normalizers import (
    normalize_submission,
)


def test_normalizer_derives_restaurant_occupancy() -> None:
    submission = InsuranceSubmission(
        submission_id="SUB-2026-0050",
        product_line=ProductLine.COMMERCIAL_PROPERTY,
        business_activity="Restaurant",
    )

    normalized_submission = normalize_submission(submission)

    assert normalized_submission.occupancy_type == "restaurant"


def test_normalizer_derives_warehouse_occupancy() -> None:
    submission = InsuranceSubmission(
        submission_id="SUB-2026-0051",
        product_line=ProductLine.COMMERCIAL_PROPERTY,
        business_activity="Warehouse",
    )

    normalized_submission = normalize_submission(submission)

    assert normalized_submission.occupancy_type == "warehouse"


def test_normalizer_preserves_explicit_occupancy_type() -> None:
    submission = InsuranceSubmission(
        submission_id="SUB-2026-0052",
        product_line=ProductLine.COMMERCIAL_PROPERTY,
        business_activity="Restaurant",
        occupancy_type="Full-service restaurant with commercial kitchen",
    )

    normalized_submission = normalize_submission(submission)

    assert normalized_submission.occupancy_type == "Full-service restaurant with commercial kitchen"
