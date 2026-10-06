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
- Claims history requires an explicit status to distinguish no losses reported from missing claims information.
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

## Ground Truth Refinement

The retail incomplete case was updated after review because the source text mentions Montreal but does not explicitly provide a province. The expected location_province value is therefore null, and the field must be reported as missing.

The evaluation policy distinguishes between:
- explicit geographic information, which can be extracted and normalized;
- geographic information inferred from common knowledge, which must not be added;
- explicit coverage wording, which can be mapped to controlled coverage values;
- product line wording alone, which must not automatically create coverage requests.

## Multi-Run Provider Stability Evaluation

Both providers were evaluated three times against the four-case synthetic
insurance submission golden dataset.

| Provider | Model | Completed Runs | Passed Cases | Total Cases | Pass Rate |
|---|---|---:|---:|---:|---:|
| Gemini | gemini-3.7-flash | 3 | 11 | 12 | 91.7% |
| Groq | openai/gpt-oss-120b | 3 | 12 | 12 | 100.0% |

## Observed Gemini Failure

Gemini intermittently omitted the property_damage coverage from the
restaurant_complete case, despite explicit property coverage wording in the
source submission.

This failure occurred once across three runs.

## Current Provider Decision

For the current MVP and the current synthetic benchmark:

- Primary provider: Gemini / gemini-3.7-flash
- Fallback candidate: Groq / openai/gpt-oss-120b
- Gemini stability: 12/12 passed across 3 runs (100.0%).
- Groq stability: 15/16 passed across 4 runs (93.75%).
- Decision rationale: Gemini achieved stable completeness on the current benchmark.
- Provider choice remains configurable through environment variables.
- The provider comparison must be repeated after every significant prompt, schema,
  dataset, or model change.

## Expanded Dataset v2

A deterministic generator (`scripts/generate_golden_dataset.py`, fixed seed) produces 63 additional
synthetic submissions, stored in `data/synthetic/generated/` and combined with the four original
cases in `data/golden/insurance_submission_cases_v2.jsonl` (67 cases).

Labels are derived by running the deterministic normalizer and validators on a known oracle
submission, so expected missing fields, quality flags, and `review_required` always match the
domain rules. A test regenerates the dataset and fails if the committed files drift.

| Family | Cases | Purpose |
|---|---:|---|
| complete | 10 | Email, form, and noisy-email styles |
| french | 4 | French-language submissions |
| no_geo / no_postal / no_year / no_revenue | 15 | Absent fields must stay null (hallucination probes) |
| no_coverage | 4 | Product line wording alone must not create coverage requests |
| claims_reported / claims_none | 11 | Claim years and claims-history status |
| claim_before_build | 4 | `BUILDING_YEAR_AFTER_CLAIM` flag |
| non_property | 6 | Cyber and general liability |
| zero_revenue / zero_employees | 4 | Zero-value quality flags |
| noisy_distractors | 5 | Reference numbers, phone numbers, and a misleading "in business since 1987" |

### Metrics

Evaluation reports now include a `field_metrics` block and per-family pass rates:

- Per-field accuracy across all cases that check the field.
- Missing-field recall: expected missing fields correctly reported as missing.
- Hallucination rate: expected-missing fields that the provider nevertheless filled.
- Errored cases: provider failures are recorded and no longer abort the run.

```bash
uv run python scripts/run_evaluation.py --provider gemini \
  --dataset data/golden/insurance_submission_cases_v2.jsonl --delay-seconds 1
uv run python scripts/run_evaluation.py --provider groq \
  --dataset data/golden/insurance_submission_cases_v2.jsonl --delay-seconds 1
```

### Status

Provider results on dataset v2 have not been recorded yet. Do not compare them with the
four-case results above, which used a different dataset. Record the new baseline here after
running both providers, ideally three runs each.

## Dataset v2 Provider Baseline (2026-10-05)

Three runs per provider on `insurance_submission_cases_v2.jsonl` (67 synthetic cases), after the
evaluator fixes (Unicode NFC matching, case-insensitive acceptable values, French activity
aliases). The benchmark is template-generated and measures relative provider behavior, not
production accuracy.

| Provider | Model | Runs | Passed | Total | Pass rate | Per-run range | Provider errors | Hallucinated / probes |
|---|---|---:|---:|---:|---:|---:|---:|---:|
| Gemini | gemini-3.7-flash | 3 | 199 | 201 | 99.0% | 98.5%-100.0% | 0 | 0 / 93 |
| Groq | openai/gpt-oss-120b | 3 | 179 | 201 | 89.1% | 86.6%-91.0% | 2 | 1 / 93 |

Groq's two provider errors (gen_claims_reported_03) are counted as failed cases. Excluding them,
Groq passes 179 of 199 completed cases (89.9%).

### Gemini Findings

- Every case passed in every run except `restaurant_complete`, where `property_damage` was
  dropped in two of three runs (`['business_interruption']` returned instead of
  `['property_damage', 'business_interruption']`). The same intermittent failure was observed in
  the earlier four-case benchmark, so it is a stable weakness, not noise.
- Field accuracy was 100% for all other fields in all three runs.

### Groq Findings

- Inferred `location_province` for `retail_incomplete` once (Montreal to QC), violating the
  no-inference policy. This is the only hallucination in 186 provider probes.
- Returned `Ltee` instead of `Ltée` for the same insured name in several cases; this is a
  genuine model-side accent change, not an evaluator artifact.
- Returned null for `annual_revenue_cad` in several runs (French and zero-employee cases),
  returned null for `business_package` in `gen_french_04` in two runs, and once converted
  `not_provided` claims history to `no_losses_reported`.

### Decision

Gemini remains the primary provider (99.0% against 89.1%, and no policy violation).
Groq stays a configurable fallback only; any fallback output should be routed to human review
because of its revenue omissions and its single province inference.

Next engineering work, in order: fix the Gemini coverage omission through the prompt or a
post-extraction consistency check, add a deterministic cross-check that flags any extracted
value absent from the source text, and implement automatic provider fallback with review flagging.

## Coverage Prompt Fix Validation (2026-10-05)

The extraction prompt now instructs the model to return every coverage the submission names,
and maps commercial property coverage, property insurance, and building and contents coverage
to `property_damage` even when listed with other coverages. Six regression cases were added
(family `coverage_phrasing`, dataset v2 now has 73 cases; the first 67 are unchanged).

A targeted run covered `restaurant_complete` plus the six new cases (7 cases, one run each).

| Provider | Passed | requested_coverages | Notes |
|---|---:|---:|---|
| Gemini | 7/7 | 7/7 | The previously unstable `restaurant_complete` case passed. |
| Groq | 5/7 | 7/7 | Failures concern revenue and insured name, not coverages. |

A single run is weak evidence: before the fix, Gemini failed `restaurant_complete` in two of
three runs. Treat the fix as promising, not proven, until the next full run on the 73-case
dataset also shows no regression on the original cases.

## Full Dataset v2 Validation (2026-10-05)

One full run on the 73-case dataset (67 original v2 cases plus six `coverage_phrasing` regression
cases), after the coverage prompt fix and the completeness-based provider fallback.

| System | Passed | Errors | Hallucination rate | Missing-field recall | Fallback used |
|---|---:|---:|---:|---:|---:|
| Gemini alone | 73/73 (100.0%) | 0 | 0.0% | 1.0 | n/a |
| Gemini + Groq fallback | 73/73 (100.0%) | 0 | 0.0% | 1.0 | 0 cases |

The previously unstable `restaurant_complete` case passed, and all per-field accuracies were
100%. The fallback never triggered, so the combined system behaved identically to Gemini alone
on this benchmark; its value is protection against provider outages and omitted fields.

Caveats: one run per system, synthetic template-generated inputs, and a dataset that was
extended to target a known failure. Before the fix Gemini passed 99.0% over three runs, so a
single 100% run is encouraging but not proof of stability. The fallback's behavior under a real
provider outage is covered by unit tests only.

## Edge-Case Expansion and Normalizer Fixes (2026-10-06)

Dataset v2 grew from 73 to 97 cases with 24 deterministic edge cases in five families:
`number_formats` (7), `partial_address` (6), `accented_city` (3), `ambiguous_activity` (4) and
`multi_site` (4). The first 73 cases are unchanged. A multi-site case uses the first named
location as the oracle because the schema holds a single location.

The first Gemini run on the 24 new cases passed 16/24 (66.7%) with 0 hallucinations. It exposed
two defects in deterministic code, not in the prompt:

| Defect | Symptom | Fix |
|---|---|---|
| Postal codes kept the source format (`t4m1v0`, `M0A-7E1`, `B8C9G9`) | 6 cases failed `postal_code` (16/22) | `normalize_postal_code` canonicalizes to `A1A 1A1`; other values are left unchanged |
| French activity keys in the occupancy mapping were stored in decomposed Unicode (base letter plus combining accent) | `magasin de détail` and `entrepôt` never matched, `occupancy_type` stayed empty and `review_required` was wrongly true (4 cases) | Lookup now ignores case, accents and Unicode composition; `commerce de détail` was added |

The second defect affected any real French submission for a retail store or a warehouse, not only
the benchmark. After the fixes the 24 new cases passed 24/24.

| Run (97 cases) | Passed | Errors | Hallucination rate | Missing-field recall |
|---|---:|---:|---:|---:|
| Gemini alone, run 1 | 97/97 (100.0%) | 0 | 0.0% | 1.0 |
| Gemini alone, run 2 | 96/97 (99.0%) | 1 | 0.0% | 1.0 |
| Gemini + Groq fallback | 97/97 (100.0%) | 0 | 0.0% | 1.0 |

In run 2 the only failure was `gen_no_revenue_01`, a transient Gemini request error
(`provider_error`), not an extraction mistake. That run was intended to include the Groq
fallback, but the evaluation runner passes the fallback provider explicitly and ignores the
`LLM_FALLBACK_PROVIDER` environment variable, so it measured Gemini alone. The combined system
was then run with `--fallback-provider groq`: it passed 97/97 and the fallback served
0 of 97 cases, so it behaved like Gemini alone on this benchmark.

Caveats: the new cases were written to expose these defects, so 100% on them is a regression
guard rather than an estimate of real-world accuracy. The two Gemini runs differ by one transient
error, which shows run-to-run variance.

### Fallback under a simulated Gemini outage

To exercise the fallback for real, Gemini was run with an invalid API key and the Groq fallback
enabled on 14 cases (`gen_complete` and `gen_french`).

| Measure | Result |
|---|---|
| Cases served by Groq | 14/14 (`openai/gpt-oss-120b`) |
| Field accuracy | 100% on every field (14/14) |
| Cases passed by the harness | 0/14 |
| Only failing check | `review_required`: expected false, got true |

The harness failures are by design, not extraction errors. When the fallback answers, the
extractor sets `review_required` and records a note naming the failed primary provider, so a
person checks results produced by the secondary model. The golden expectations assume the
primary provider and therefore expect no review. The result confirms that the fallback works end
to end and is visible to the caller; a separate expectation for fallback runs is a possible
improvement to the harness. Two identical runs gave the same result.

## Limitations

- The original benchmark contains only four synthetic cases; dataset v2 adds 63 template-generated cases, which are still synthetic and more regular than real broker emails.
- A valid structured response does not guarantee factual correctness.
- Before production use, extend the golden dataset with anonymized or representative
  broker submissions, additional incomplete cases, ambiguous locations, multiple
  locations, claims-history variations, and adversarial inputs.
