from __future__ import annotations

from collections import Counter

from insurance_submission_extractor.schemas import (
    ClaimsHistoryStatus,
    DataQualityFlag,
    DataQualitySeverity,
    InsuranceSubmission,
    ProductLine,
    ValidationReport,
)

CANADIAN_PROVINCE_CODES = {
    "AB",
    "BC",
    "MB",
    "NB",
    "NL",
    "NS",
    "NT",
    "NU",
    "ON",
    "PE",
    "QC",
    "SK",
    "YT",
}

BASE_REQUIRED_FIELDS = (
    "product_line",
    "business_activity",
    "location_city",
    "location_province",
    "postal_code",
    "annual_revenue_cad",
    "requested_coverages",
)

PROPERTY_REQUIRED_FIELDS = (
    "building_construction_year",
    "occupancy_type",
)


def get_missing_fields(submission: InsuranceSubmission) -> list[str]:
    required_fields = list(BASE_REQUIRED_FIELDS)

    if submission.product_line in {
        ProductLine.COMMERCIAL_PROPERTY,
        ProductLine.BUSINESS_PACKAGE,
    }:
        required_fields.extend(PROPERTY_REQUIRED_FIELDS)

    missing_fields: list[str] = []

    for field_name in required_fields:
        value = getattr(submission, field_name)

        if value is None:
            missing_fields.append(field_name)
            continue

        if isinstance(value, str) and not value.strip():
            missing_fields.append(field_name)
            continue

        if isinstance(value, list) and not value:
            missing_fields.append(field_name)

    return missing_fields


def validate_submission(submission: InsuranceSubmission) -> ValidationReport:
    flags: list[DataQualityFlag] = []
    missing_fields = get_missing_fields(submission)

    if submission.location_province and submission.location_province not in CANADIAN_PROVINCE_CODES:
        flags.append(
            DataQualityFlag(
                field="location_province",
                severity=DataQualitySeverity.WARNING,
                code="UNRECOGNIZED_PROVINCE_CODE",
                message=(
                    "Location province is not a recognized Canadian province or territory code."
                ),
            )
        )

    if submission.annual_revenue_cad == 0:
        flags.append(
            DataQualityFlag(
                field="annual_revenue_cad",
                severity=DataQualitySeverity.WARNING,
                code="ZERO_REVENUE",
                message="Annual revenue is zero and should be confirmed.",
            )
        )

    if submission.employee_count == 0:
        flags.append(
            DataQualityFlag(
                field="employee_count",
                severity=DataQualitySeverity.INFO,
                code="ZERO_EMPLOYEES",
                message="Employee count is zero and may indicate a sole proprietorship.",
            )
        )

    if submission.building_construction_year and submission.claims_history:
        latest_claim_year = max(claim.year for claim in submission.claims_history)

        if submission.building_construction_year > latest_claim_year:
            flags.append(
                DataQualityFlag(
                    field="building_construction_year",
                    severity=DataQualitySeverity.WARNING,
                    code="BUILDING_YEAR_AFTER_CLAIM",
                    message=(
                        "Building construction year is later than the most recent"
                        " reported claim year."
                    ),
                )
            )

    claim_identifiers = [
        (claim.year, claim.claim_type, claim.amount_cad) for claim in submission.claims_history
    ]
    duplicate_claims = [
        identifier for identifier, count in Counter(claim_identifiers).items() if count > 1
    ]

    if duplicate_claims:
        flags.append(
            DataQualityFlag(
                field="claims_history",
                severity=DataQualitySeverity.WARNING,
                code="POSSIBLE_DUPLICATE_CLAIMS",
                message="Potential duplicate claim records were detected.",
            )
        )

    if submission.claims_history_status == ClaimsHistoryStatus.NOT_PROVIDED:
        flags.append(
            DataQualityFlag(
                field="claims_history",
                severity=DataQualitySeverity.INFO,
                code="CLAIMS_HISTORY_NOT_PROVIDED",
                message="No claims history was provided in the submission.",
            )
        )

    review_required = bool(missing_fields) or any(
        flag.severity == DataQualitySeverity.ERROR for flag in flags
    )

    return ValidationReport(
        missing_fields=missing_fields,
        data_quality_flags=flags,
        review_required=review_required,
    )
