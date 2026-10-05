from insurance_submission_extractor.schemas import (
    ClaimRecord,
    ClaimType,
    CoverageType,
    InsuranceSubmission,
    ProductLine,
)
from insurance_submission_extractor.services.evidence import find_field_evidence


def evidence(text: str, **fields: object):
    submission = InsuranceSubmission(submission_id="S", **fields)
    references, unsupported = find_field_evidence(text, submission)

    return {ref.field_name: ref.source_excerpt for ref in references}, unsupported


def test_supported_values_return_the_passage() -> None:
    text = (
        "Le Jardin Bistro is a restaurant in Montreal, Quebec H2X 1Y4.\n"
        "The building was constructed in 1998. We have 24 employees.\n"
        "Estimated annual revenue is CAD 1,200,000."
    )
    found, unsupported = evidence(
        text,
        insured_name="Le Jardin Bistro",
        location_city="Montreal",
        location_province="QC",
        postal_code="H2X1Y4",
        building_construction_year=1998,
        employee_count=24,
        annual_revenue_cad=1_200_000,
    )

    assert unsupported == []
    assert "constructed in 1998" in found["building_construction_year"]
    assert "1,200,000" in found["annual_revenue_cad"]


def test_province_inferred_from_city_is_unsupported() -> None:
    _, unsupported = evidence("A restaurant located in Montreal.", location_province="QC")

    assert unsupported == ["location_province"]


def test_two_letter_code_does_not_match_english_word() -> None:
    _, unsupported = evidence("Please advise on pricing for our shop.", location_province="ON")

    assert unsupported == ["location_province"]


def test_year_without_construction_context_is_unsupported() -> None:
    text = "The company has been in business since 1987."
    _, unsupported = evidence(text, building_construction_year=1987)

    assert unsupported == ["building_construction_year"]


def test_accents_and_number_formats_are_tolerated() -> None:
    text = "Boutique Beaulieu Ltée. Revenus annuels: 2,5 M$. Employés: 21."
    found, unsupported = evidence(
        text,
        insured_name="Boutique Beaulieu Ltee",
        annual_revenue_cad=2_500_000,
        employee_count=21,
    )

    assert unsupported == []
    assert set(found) == {"insured_name", "annual_revenue_cad", "employee_count"}


def test_invented_revenue_and_claim_year_are_unsupported() -> None:
    text = "Annual revenue is CAD 900,000. One water damage claim in 2023."
    _, unsupported = evidence(
        text,
        annual_revenue_cad=950_000,
        claims_history=[
            ClaimRecord(year=2021, claim_type=ClaimType.WATER_DAMAGE, amount_cad=18000)
        ],
    )

    assert unsupported == ["annual_revenue_cad", "claims_history"]


def test_product_line_and_coverages_need_matching_wording() -> None:
    _, unsupported = evidence(
        "We want commercial property insurance for our restaurant.",
        product_line=ProductLine.CYBER,
        requested_coverages=[CoverageType.PROPERTY_DAMAGE, CoverageType.CYBER_LIABILITY],
    )

    assert unsupported == ["product_line", "requested_coverages"]
