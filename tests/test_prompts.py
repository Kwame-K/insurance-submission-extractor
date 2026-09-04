from insurance_submission_extractor.prompts import (
    SYSTEM_INSTRUCTIONS,
    build_extraction_prompt,
)


def test_extraction_prompt_contains_submission_id_and_text() -> None:
    prompt = build_extraction_prompt(
        submission_id="SUB-2026-0020",
        submission_text="A restaurant in Montreal requests property coverage.",
    )

    assert "SUB-2026-0020" in prompt
    assert "restaurant in Montreal" in prompt


def test_system_instructions_prohibit_hallucinated_data() -> None:
    assert "Do not infer, estimate, or invent" in SYSTEM_INSTRUCTIONS
    assert "Do not make underwriting decisions." in SYSTEM_INSTRUCTIONS


def test_system_instructions_define_extraction_policies() -> None:
    assert "business_activity" in SYSTEM_INSTRUCTIONS
    assert 'product_line "commercial_property"' in SYSTEM_INSTRUCTIONS
    assert "Do not infer requested_coverages" in SYSTEM_INSTRUCTIONS
    assert 'claims_history_status to "no_losses_reported"' in SYSTEM_INSTRUCTIONS


def test_system_instructions_define_location_and_coverage_policies() -> None:
    assert "Do not infer location_province from location_city alone." in (SYSTEM_INSTRUCTIONS)
    assert "Do not infer postal_code from a city" in SYSTEM_INSTRUCTIONS
    assert 'requested_coverages value "property_damage"' in SYSTEM_INSTRUCTIONS
    assert "Commercial property insurance alone identifies product_line" in (SYSTEM_INSTRUCTIONS)
