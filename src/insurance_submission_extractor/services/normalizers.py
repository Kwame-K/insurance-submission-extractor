from __future__ import annotations

from insurance_submission_extractor.schemas import InsuranceSubmission

OCCUPANCY_BY_BUSINESS_ACTIVITY = {
    "restaurant": "restaurant",
    "retail store": "retail store",
    "small retail store": "retail store",
    "warehouse": "warehouse",
}


def normalize_submission(
    submission: InsuranceSubmission,
) -> InsuranceSubmission:
    if submission.occupancy_type is not None:
        return submission

    if submission.business_activity is None:
        return submission

    normalized_activity = submission.business_activity.strip().lower()

    occupancy_type = OCCUPANCY_BY_BUSINESS_ACTIVITY.get(normalized_activity)

    if occupancy_type is None:
        return submission

    return submission.model_copy(
        update={
            "occupancy_type": occupancy_type,
        }
    )
