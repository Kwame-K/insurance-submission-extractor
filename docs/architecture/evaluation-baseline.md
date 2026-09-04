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
