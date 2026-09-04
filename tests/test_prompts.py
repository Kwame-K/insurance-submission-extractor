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
