from __future__ import annotations

import re

from insurance_submission_extractor.schemas import CoverageType, InsuranceSubmission

_POSTAL_CODE = re.compile(r"\b[A-Z]\d[A-Z][ -]?\d[A-Z]\d\b", re.IGNORECASE)
_EMPLOYEES = re.compile(r"\b\d+\s+(?:employees|employ[eé]s|staff members)\b", re.IGNORECASE)
_YEAR_BUILT = re.compile(
    r"\b(?:constructed|built|construit[e]?)\s+(?:in|en)\s+(?:1[89]|20)\d{2}\b",
    re.IGNORECASE,
)
_REVENUE = re.compile(r"\b(?:revenue|revenus?)\b[^.\n]{0,60}?\d", re.IGNORECASE)
_PROPERTY_COVERAGE = re.compile(
    r"\b(?:property|building and contents)\b[^.\n]{0,30}\bcoverage\b"
    r"|property damage|dommages aux biens",
    re.IGNORECASE,
)
_BUSINESS_INTERRUPTION = re.compile(
    r"business interruption|interruption des affaires",
    re.IGNORECASE,
)


def find_completeness_gaps(submission_text: str, submission: InsuranceSubmission) -> list[str]:
    """Return fields that the source text states explicitly but the extraction left empty.

    The checks are deliberately conservative: they never infer values, and product
    wording alone (for example "commercial property insurance") is not treated as a
    coverage request.
    """
    gaps: list[str] = []

    if submission.annual_revenue_cad is None and _REVENUE.search(submission_text):
        gaps.append("annual_revenue_cad")

    if submission.employee_count is None and _EMPLOYEES.search(submission_text):
        gaps.append("employee_count")

    if submission.building_construction_year is None and _YEAR_BUILT.search(submission_text):
        gaps.append("building_construction_year")

    if submission.postal_code is None and _POSTAL_CODE.search(submission_text):
        gaps.append("postal_code")

    coverages = set(submission.requested_coverages)
    missing_coverage = (
        _PROPERTY_COVERAGE.search(submission_text) and CoverageType.PROPERTY_DAMAGE not in coverages
    ) or (
        _BUSINESS_INTERRUPTION.search(submission_text)
        and CoverageType.BUSINESS_INTERRUPTION not in coverages
    )
    if missing_coverage:
        gaps.append("requested_coverages")

    return gaps
