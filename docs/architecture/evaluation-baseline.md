# Extraction Evaluation Baseline

## Purpose

This document records manual baseline evaluations for the insurance submission
extractor before provider comparison and automated evaluation are introduced.

## Evaluation Criteria

| Criterion | Description |
|---|---|
| Schema validity | The output conforms to the Pydantic contract. |
| Field extraction accuracy | Explicit source information is extracted correctly. |
| Missing data handling | Unstated information remains null or is listed as missing. |
| Normalization accuracy | Provinces, coverages, product lines, and claim types use approved values. |
| Hallucination rate | The extractor does not create unsupported facts. |
| Business validation | Deterministic rules generate expected quality flags. |

## Baseline Cases

| Case ID | Scenario | Expected Outcome | Status |
|---|---|---|---|
| SUB-2026-0001 | Complete restaurant property submission | Structured extraction with no quality flags | Passed |
| SUB-2026-0002 | Incomplete retail property submission | Missing fields detected and review required | Passed |
| SUB-2026-0003 | Inconsistent warehouse submission | Building year after claim flag detected | Passed |
| SUB-2026-0004 | Cyber submission | Cyber classification without property requirements | Passed after claims-history status refinement |


## Notes

- All input data is synthetic.
- Manual evaluations must document factual extraction errors.
- A valid JSON response does not prove factual accuracy.
- Provider comparisons must use identical source submissions.

## Findings

- A syntactically valid structured response does not guarantee semantic completeness.
- Claims history requires an explicit status to distinguish no losses reported
  from missing claims information.
- Deterministic validation rules successfully detected an impossible temporal
  relationship between a building construction year and a prior claim.
- Business activity and occupancy type must remain separate concepts.

## Provider Comparison

| Case ID | Scenario | Gemini Result | Groq Result | Notes |
|---|---|---|---|---|
| SUB-2026-0001 | Complete restaurant property submission | Passed | Partially passed | Groq returned null for occupancy_type; policy decision required on activity-to-occupancy normalization. |
| SUB-2026-0002 | Incomplete retail property submission | Passed | Partially passed | Groq inferred property_damage from the product line although no explicit coverage was requested. |
| SUB-2026-0003 | Inconsistent warehouse submission | Passed | Passed | Both providers extracted the underlying facts; deterministic validation raised BUILDING_YEAR_AFTER_CLAIM. |
| SUB-2026-0004 | Cyber submission | Passed after claims-history refinement | Partially passed | Groq correctly identified no_losses_reported but failed to extract the explicit data consulting business activity. |

## Provider Findings

- Both providers produced schema-valid Pydantic-compatible outputs.
- Provider outputs differ despite an identical prompt, schema, and synthetic source file.
- Gemini extracted business_activity more consistently in the evaluated cyber case.
- Groq followed a more conservative strategy for occupancy_type in the restaurant case.
- Groq inferred property_damage from commercial property insurance, which requires a stricter prompt policy.
- Deterministic Python validation produced consistent risk flags regardless of the provider.
- Structured output guarantees output shape, not field-level factual correctness.
