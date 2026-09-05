# Insurance Submission Extractor

[![Continuous Integration](../../actions/workflows/ci.yml/badge.svg)](../../actions/workflows/ci.yml)

A provider-agnostic LLM application that converts unstructured commercial insurance submissions into validated, structured data.

The project combines structured LLM outputs, Pydantic data contracts, deterministic insurance-domain normalization, business-rule validation, review routing, and a versioned evaluation dataset. It is designed as the first building block of a future agentic underwriting workflow.

## Problem

Commercial insurance submissions are often received as unstructured broker emails, documents, or free-text forms. Before an underwriter can assess eligibility, pricing, and risk, the submission must be converted into consistent and validated fields.

This project extracts structured information such as:

- Product line and requested coverages
- Insured name and business activity
- Location and building characteristics
- Employee count and annual revenue
- Claims history and claims-history status
- Missing information and data-quality issues
- Human-review requirement

The application does not make underwriting decisions, accept or decline risks, or calculate premiums. It focuses on trustworthy data extraction and validation.

## Key Features

- Provider-agnostic LLM architecture
- Gemini support through `gemini-3.7-flash`
- Groq support through `openai/gpt-oss-120b`
- Structured JSON extraction with Pydantic validation
- Insurance-domain enums for product lines, coverages, claim types, and data-quality severity
- Deterministic normalization of business activity into occupancy type
- Deterministic data-quality validation rules
- Explicit distinction between missing claims history and explicitly reported no-loss history
- `review_required` routing signal for incomplete submissions
- Versioned synthetic golden dataset
- Multi-provider regression evaluation runner
- Automated formatting, linting, and tests through GitHub Actions

## Architecture

```text
                         Unstructured Submission
                                   |
                                   v
                         SubmissionExtractor
                                   |
                                   v
                      Provider-Agnostic LLM Client
                         /                     \
                        v                       v
            GeminiClient                 GroqClient
        gemini-3.7-flash          openai/gpt-oss-120b
                         \                     /
                          v                   v
                    Structured JSON Extraction
                                   |
                                   v
                     Pydantic Schema Validation
                                   |
                                   v
              Deterministic Domain Normalization
              business_activity -> occupancy_type
                                   |
                                   v
              Deterministic Business Rule Validation
                                   |
                                   v
               ExtractionResult + review_required
                                   |
                                   v
                Golden Dataset Evaluation Runner
```

## Project Structure

```text
insurance-submission-extractor/
├── .github/workflows/ci.yml
├── data/
│   ├── golden/
│   │   └── insurance_submission_cases.jsonl
│   ├── evaluations/
│   └── synthetic/
├── docs/
│   └── architecture/
│       └── evaluation-baseline.md
├── scripts/
│   └── run_evaluation.py
├── src/
│   └── insurance_submission_extractor/
│       ├── llm/
│       │   ├── base.py
│       │   ├── factory.py
│       │   ├── gemini_client.py
│       │   └── groq_client.py
│       ├── prompts/
│       │   └── extraction_prompt.py
│       ├── schemas/
│       │   └── submission.py
│       ├── services/
│       │   ├── extractor.py
│       │   ├── normalizers.py
│       │   └── validators.py
│       ├── cli.py
│       ├── config.py
│       └── evaluation.py
├── tests/
├── .env.example
├── pyproject.toml
└── uv.lock
```

## Technology Stack

| Area | Technology |
|---|---|
| Language | Python 3.11+ |
| Environment and dependencies | uv |
| LLM providers | Google Gemini and Groq |
| LLM models | gemini-3.7-flash and openai/gpt-oss-120b |
| Structured data | Pydantic |
| Testing | pytest and pytest-cov |
| Linting and formatting | Ruff |
| CI | GitHub Actions |

## Setup

### Prerequisites

- Python 3.11 or later
- [uv](https://docs.astral.sh/uv/)
- A Gemini API key, a Groq API key, or both

### Installation

```bash
git clone <your-repository-url>
cd insurance-submission-extractor
uv sync --all-groups
```

### Environment Configuration

Create a local environment file:

```bash
cp .env.example .env
```

Configure at least one provider in `.env`:

```dotenv
LLM_PROVIDER=groq

GROQ_API_KEY=your_groq_api_key
GROQ_MODEL=openai/gpt-oss-120b
GROQ_MAX_RETRIES=3

GEMINI_API_KEY=your_gemini_api_key
GEMINI_MODEL=gemini-3.7-flash
```

Do not commit `.env` files or API keys.

## Usage

### Extract a Submission

Run the CLI against a synthetic submission:

```bash
uv run insurance-submission-extractor \
  --input-file data/synthetic/restaurant_submission.txt \
  --submission-id SUB-2026-0001
```

Example output:

```json
{
  "submission": {
    "submission_id": "SUB-2026-0001",
    "product_line": "commercial_property",
    "insured_name": "Le Jardin Bistro",
    "business_activity": "restaurant",
    "location_city": "Montreal",
    "location_province": "QC",
    "postal_code": "H2X 1Y4",
    "building_construction_year": 1998,
    "occupancy_type": "restaurant",
    "employee_count": 24,
    "annual_revenue_cad": 1200000.0,
    "requested_coverages": [
      "property_damage",
      "business_interruption"
    ],
    "claims_history_status": "losses_reported"
  },
  "missing_fields": [],
  "data_quality_flags": [],
  "review_required": false,
  "provider": "groq",
  "model": "openai/gpt-oss-120b"
}
```

### Switch Providers

Choose the provider through the environment configuration:

```dotenv
LLM_PROVIDER=gemini
```

or:

```dotenv
LLM_PROVIDER=groq
```

The extraction schema, normalization, validation rules, CLI, and evaluation logic remain unchanged.

## Validation Strategy

The project deliberately separates LLM behavior from deterministic business logic.

```text
LLM extraction
    +
Pydantic structural validation
    +
Deterministic normalization
    +
Deterministic business validation
    =
Auditable extraction pipeline
```

### Pydantic Validation

Pydantic validates:

- Data types and numeric constraints
- Allowed product lines, coverage types, and claim types
- Future claim years
- Contradictory claims-history statuses
- JSON output compatibility with the application contract

### Domain Normalization

The application applies deterministic mappings after LLM extraction. For example:

```text
business_activity = "Restaurant"
        |
        v
occupancy_type = "restaurant"
```

Explicit occupancy information is preserved and never overwritten by a derived value.

### Business Validation

The validation layer identifies:

- Missing required fields
- Missing claims-history information
- Unrecognized province or territory codes
- Zero revenue or zero employee counts requiring confirmation
- Duplicate claim records
- Building construction years later than reported claim years

The `review_required` field is a routing signal for a future human-in-the-loop underwriting workflow.

## Evaluation

The application includes a versioned JSONL golden dataset containing synthetic insurance submissions and expected outputs.

Run the evaluation suite with Gemini:

```bash
uv run python scripts/run_evaluation.py --provider gemini
```

Run the evaluation suite with Groq:

```bash
uv run python scripts/run_evaluation.py --provider groq
```

Each evaluation run:

1. Loads the synthetic golden cases.
2. Sends each case to the selected provider.
3. Runs deterministic normalization and business validation.
4. Compares extracted values, expected missing fields, flags, and review routing.
5. Records a timestamped JSON report in `data/evaluations/`.

### Current Baseline

The current benchmark contains four synthetic English-language submissions:

| Case | Scenario | Validation Focus |
|---|---|---|
| `restaurant_complete` | Complete commercial property submission | Full extraction of property and business interruption coverage |
| `retail_incomplete` | Incomplete commercial property submission | Missing-field detection and human-review routing |
| `warehouse_inconsistent` | Building year later than a prior fire claim | Deterministic temporal inconsistency detection |
| `cyber_no_losses` | Cyber submission with explicitly reported no-loss history | Product classification and claims-history status |

In the current three-run synthetic benchmark:

| Provider | Model | Passed Cases | Total Cases | Pass Rate |
|---|---|---:|---:|---:|
| Gemini | gemini-3.7-flash | 11 | 12 | 91.7% |
| Groq | openai/gpt-oss-120b | 12 | 12 | 100.0% |

These results are limited to the current four-case synthetic dataset and must not be treated as a general provider benchmark.

## Quality Checks

Run all local checks before committing:

```bash
uv run ruff format --check .
uv run ruff check .
uv run pytest
```

Format the project locally:

```bash
uv run ruff format .
```

The GitHub Actions workflow runs formatting checks, linting, and tests on pushes and pull requests to `main`.

## Limitations

- The dataset contains only four synthetic English-language examples.
- The evaluation suite does not yet measure token usage, cost, confidence calibration, or retrieval quality.
- The project does not yet support document ingestion, OCR, RAG, vector search, database persistence, or a web API.
- Business-rule coverage is intentionally limited and does not represent an insurer's production underwriting rules.
- `review_required` is a routing signal only; it does not yet pause a workflow for human approval.
- The project does not make underwriting decisions, bind coverage, calculate premiums, or replace qualified insurance professionals.
- All examples are synthetic and must not be interpreted as real insurance data or underwriting guidance.

## Roadmap

This project is the first stage of a broader agentic insurance and risk platform.

### Project 2: Data Analyst Agent

- Tool calling for controlled SQL and Python analytics
- Portfolio metrics, claims summaries, and chart generation
- Auditable tool execution

### Project 3: Insurance Knowledge Agent

- Insurance documents ingestion
- PostgreSQL and pgvector
- Retrieval, reranking, citations, and grounded answers

### Project 4: Underwriting Agent

- LangGraph workflow orchestration
- Submission extraction, validation, retrieval, analytics, pricing, and recommendation
- Human-in-the-loop review gates
- Underwriting report generation

### Project 5: Multi-Agent Risk Committee

- Orchestrator, data, actuary, risk, underwriter, and reviewer agents
- Explicit roles, evidence sharing, verification, and escalation

### Project 6: Production Agent Platform

- FastAPI backend
- PostgreSQL persistence and Redis cache
- Docker deployment
- Observability, evaluation, access control, and CI/CD

## Development Principles

- Do not trust unvalidated LLM output.
- Do not infer missing underwriting data without an explicit, tested business rule.
- Keep extraction, normalization, validation, and decision logic separate.
- Use synthetic or anonymized data only.
- Version prompts, schemas, rules, datasets, and evaluation results.
- Prefer deterministic controls for high-impact business rules.
- Preserve human review for incomplete, inconsistent, or high-risk cases.

## License

This project is intended for educational and portfolio purposes. Add a license appropriate for your intended use before sharing or deploying it publicly.

## Author

Built by Kristian Laban.

- GitHub: [@Kwame-K](https://github.com/Kwame-K)
- LinkedIn: [Kwame Kristian LABAN](https://www.linkedin.com/in/kwame-kristian-laban/)

