import unicodedata

import pytest

from insurance_submission_extractor.schemas import InsuranceSubmission, ProductLine
from insurance_submission_extractor.services.normalizers import (
    normalize_postal_code,
    normalize_submission,
)


def submission(**fields: object) -> InsuranceSubmission:
    return InsuranceSubmission(
        submission_id="N-1", product_line=ProductLine.COMMERCIAL_PROPERTY, **fields
    )


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("t4m1v0", "T4M 1V0"),
        ("M0A-7E1", "M0A 7E1"),
        ("B8C9G9", "B8C 9G9"),
        (" h2x  1y4 ", "H2X 1Y4"),
        ("H2X 1Y4", "H2X 1Y4"),
    ],
)
def test_postal_codes_are_canonicalized(raw: str, expected: str) -> None:
    assert normalize_postal_code(raw) == expected


@pytest.mark.parametrize("raw", ["12345", "ABC123", "H2X 1Y", "90210-1234", ""])
def test_values_that_are_not_postal_codes_are_left_alone(raw: str) -> None:
    assert normalize_postal_code(raw) == raw


def test_normalization_rewrites_the_submission_postal_code() -> None:
    result = normalize_submission(submission(postal_code="v9x1l2"))

    assert result.postal_code == "V9X 1L2"


@pytest.mark.parametrize("form", ["NFC", "NFD"])
@pytest.mark.parametrize(
    ("activity", "occupancy"),
    [
        ("entrepôt", "warehouse"),
        ("magasin de détail", "retail store"),
        ("Magasin de Détail", "retail store"),
        ("commerce de détail", "retail store"),
    ],
)
def test_french_activities_infer_occupancy_in_any_unicode_form(
    form: str, activity: str, occupancy: str
) -> None:
    result = normalize_submission(
        submission(business_activity=unicodedata.normalize(form, activity))
    )

    assert result.occupancy_type == occupancy


def test_explicit_occupancy_is_never_overwritten() -> None:
    result = normalize_submission(
        submission(business_activity="warehouse", occupancy_type="cold storage")
    )

    assert result.occupancy_type == "cold storage"
