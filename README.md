# Insurance Submission Extractor

[![Continuous Integration](../../actions/workflows/ci.yml/badge.svg)](../../actions/workflows/ci.yml)

A provider-agnostic LLM application that converts unstructured commercial insurance submissions into validated, structured data.

The project combines structured LLM outputs, Pydantic data contracts, deterministic insurance-domain normalization, business-rule validation, review routing, an HTTP API, and a versioned evaluation dataset. It is the first building block (Project 1) of a larger agentic insurance platform that already includes a Data Analyst Agent (Project 2), a Knowledge Agent / RAG service (Project 3), and an Underwriting Agent (Project 4).

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

- Provider-agnostic LLM architecture (`llm/base.py`, `llm/factory.py`)
- Gemini support through `gemini-3.7-flash`
- Groq support through `openai/gpt-oss-120b`
- Structured JSON extraction with Pydantic validation
- Insurance-domain enums for product lines, coverages, claim types, and data-quality severity
- Deterministic normalization of business activity into occupancy type
- Deterministic data-quality validation rules
- Explicit distinction between missing claims history and explicitly reported no-loss history
- `review_required` routing signal for incomplete submissions
- FastAPI HTTP service (`api/app.py`) with health check and extraction endpoint
- `X-Correlation-ID` propagation for cross-service tracing with Project 4
- Dockerized service with `compose.yaml`
- Versioned synthetic golden dataset
- Multi-provider regression evaluation runner
- Automated formatting, linting, static typing, and tests through GitHub Actions

## Architecture

```text
                         Unstructured Submission
                                   |
               +-------------------+-------------------+
               v                                       v
              CLI                              FastAPI (api/app.py)
               |                                       |
               +-------------------+-------------------+
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
              (schemas/submission.py, schemas/integration.py)
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
                    +--------------+--------------+
                    v                             v
         Golden Dataset Evaluation      HTTP Response (with
              Runner                    X-Correlation-ID)
```

For a detailed architecture description, component responsibilities, sequence diagrams, evaluation flow, and future underwriting workflow, see [System Architecture](docs/architecture/system-architecture_updated.md).

## Project Structure

```text
insurance-submission-extractor/
├── .github/workflows/ci.yml
├── data/
│   ├── golden/
│   │   └── insurance_submission_cases.jsonl
│   ├── evaluations/
│   └── synthetic/
│       ├── cyber_submission.txt
│       ├── incomplete_submission.txt
│       ├── inconsistent_submission.txt
│       └── restaurant_submission.txt
├── docs/
│   ├── architecture/
│   │   ├── evaluation-baseline.md
│   │   └── system-architecture.md
│   └── extraction_http_contract.md
├── scripts/
│   └── run_evaluation.py
├── src/
│   └── insurance_submission_extractor/
│       ├── api/
│       │   └── app.py
│       ├── llm/
│       │   ├── base.py
│       │   ├── factory.py
│       │   ├── gemini_client.py
│       │   └── groq_client.py
│       ├── prompts/
│       │   └── extraction_prompt.py
│       ├── schemas/
│       │   ├── integration.py
│       │   └── submission.py
│       ├── services/
│       │   ├── extractor.py
│       │   ├── normalizers.py
│       │   └── validators.py
│       ├── cli.py
│       ├── config.py
│       └── evaluation.py
├── tests/
│   ├── test_api.py
│   ├── test_config.py
│   ├── test_evaluation.py
│   ├── test_extractor.py
│   ├── test_integration_schemas.py
│   ├── test_llm_factory.py
│   ├── test_normalizers.py
│   ├── test_prompts.py
│   ├── test_schemas.py
│   └── test_validators.py
├── .env.example
├── compose.yaml
├── Dockerfile
├── pyproject.toml
└── uv.lock
```

## Technology Stack

| Area | Technology |
|---|---|
| Language | Python 3.11+ |
| Environment and dependencies | uv |
| Web framework | FastAPI + uvicorn[standard] |
| LLM providers | Google Gemini and Groq |
| LLM models | gemini-3.7-flash and openai/gpt-oss-120b |
| Structured data | Pydantic and pydantic-settings |
| Testing | pytest and pytest-cov |
| Linting and formatting | Ruff |
| Containerization | Docker and Docker Compose |
| CI | GitHub Actions |

## Setup

### Prerequisites

- Python 3.11 or later
- [uv](https://docs.astral.sh/uv/)
- A Gemini API key, a Groq API key, or both

### Installation

```bash
git clone https://github.com/Kwame-K/insurance-submission-extractor.git
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

### Extract a Submission (CLI)

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
    "requested_coverages": ["property_damage", "business_interruption"],
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

```dotenv
LLM_PROVIDER=gemini
```
or
```dotenv
LLM_PROVIDER=groq
```

The extraction schema, normalization, validation rules, CLI, API, and evaluation logic remain unchanged across providers.

## Validation Strategy

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

- Data types and numeric constraints
- Allowed product lines, coverage types, and claim types
- Future claim years
- Contradictory claims-history statuses
- JSON output compatibility with the integration contract (`schemas/integration.py`)

### Domain Normalization

```text
business_activity = "Restaurant"
        |
        v
occupancy_type = "restaurant"
```

Explicit occupancy information is preserved and never overwritten by a derived value.

### Business Validation

- Missing required fields
- Missing claims-history information
- Unrecognized province or territory codes
- Zero revenue or zero employee counts requiring confirmation
- Duplicate claim records
- Building construction years later than reported claim years

The `review_required` field is a routing signal consumed downstream by the Underwriting Agent (Project 4).

## HTTP API

Start the API locally:

```bash
uv run uvicorn insurance_submission_extractor.api.app:app --reload
```

The service is available at `http://127.0.0.1:8000`.

| Endpoint | Purpose |
|---|---|
| GET /health | Confirms that the API process is running |
| POST /v1/extract-submission | Extracts and validates candidate data from a text-based insurance submission |
| GET /docs | Interactive OpenAPI documentation |

The API contract is documented in `docs/extraction_http_contract.md`. The consumer should send an `X-Correlation-ID` header; the service propagates the same value in its response header and generates a UUID when omitted. This allows the Underwriting Agent (Project 4) to trace one request across the Submission Extractor and the Insurance Knowledge Agent (Project 3).

## Docker

```bash
docker compose up --build          # build and start
docker compose up --build -d       # run in background
curl -i -H "X-Correlation-ID: docker-health-001" http://127.0.0.1:8000/health
docker compose down                # stop
```

This service is also orchestrated centrally by the `insurance-agentic-platform` Docker Compose project alongside the Underwriting Agent.

## Evaluation

The application includes a versioned JSONL golden dataset containing synthetic insurance submissions and expected outputs.

```bash
uv run python scripts/run_evaluation.py --provider gemini
uv run python scripts/run_evaluation.py --provider groq
```

Each evaluation run:

1. Loads the synthetic golden cases.
2. Sends each case to the selected provider.
3. Runs deterministic normalization and business validation.
4. Compares extracted values, expected missing fields, flags, and review routing.
5. Records a timestamped JSON report in `data/evaluations/`.

### Current Golden Cases

| Case | Scenario | Validation Focus |
|---|---|---|
| `restaurant_complete` | Complete commercial property submission | Full extraction of property and business interruption coverage |
| `retail_incomplete` | Incomplete commercial property submission | Missing-field detection and human-review routing |
| `warehouse_inconsistent` | Building year later than a prior fire claim | Deterministic temporal inconsistency detection |
| `cyber_no_losses` | Cyber submission with explicitly reported no-loss history | Product classification and claims-history status |

See `docs/architecture/evaluation-baseline.md` for the latest recorded pass rates by provider. Results are limited to the current four-case synthetic dataset and must not be treated as a general provider benchmark.

## Quality Checks

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

- The golden dataset contains only four synthetic English-language examples.
- The evaluation suite does not yet measure token usage, cost, confidence calibration, or retrieval quality.
- The project does not perform document ingestion, OCR, or vector search itself (this is handled by Project 3).
- Business-rule coverage is intentionally limited and does not represent an insurer's production underwriting rules.
- `review_required` is a routing signal only; it does not yet pause a workflow for human approval.
- The project does not make underwriting decisions, bind coverage, calculate premiums, or replace qualified insurance professionals.
- All examples are synthetic and must not be interpreted as real insurance data or underwriting guidance.

## Position in the Insurance Agentic Platform

This project is Project 1 of a five-project portfolio orchestrated locally through `insurance-agentic-platform`:

| Project | Repository | Role |
|---|---|---|
| 1 | insurance-submission-extractor (this repo) | Structured submission intake and validation |
| 2 | insurance-data-analyst-agent | Controlled portfolio analytics (loss ratio, deterministic SQL) |
| 3 | insurance-rag-assistant | Insurance Knowledge Agent with grounded, cited retrieval |
| 4 | underwriting-agent | Deterministic underwriting rules, risk scoring, pricing, and evidence retrieval |
| — | insurance-agentic-platform | Docker Compose orchestration layer for the running services |

## Recommended Technology Upgrades

| Area | Current | Recommended (2026) | Benefit |
|---|---|---|---|
| LLM observability | No tracing | Langfuse (self-hosted, MIT) or OpenTelemetry | Full trace of cost, latency, and provider behavior per extraction |
| Structured output generation | Manual prompt + JSON parsing | Pydantic AI or native structured-output modes | Fewer parsing failures, tighter schema guarantees at generation time |
| Persistence | Timestamped JSON files in `data/evaluations/` | PostgreSQL with SQLAlchemy 2.0 async | Queryable audit history shared with the Data Analyst Agent |
| API layer | Direct function calls in `api/app.py` | Dependency injection (`Depends()`) and repository pattern | Better testability and separation of concerns |
| Evaluation | Field-by-field comparison only | Add LLM-as-a-judge scoring (Langfuse, Confident AI) | Detects semantic drift beyond exact-field matching |
| Batch processing | Synchronous only | FastAPI `BackgroundTasks` or a lightweight queue (ARQ) | Enables bulk submission processing without blocking the API |

## Improvements and Next Steps

1. Instrument `SubmissionExtractor.extract()` with tracing (Langfuse or OpenTelemetry) capturing provider, cost, latency, and retries for every run.
2. Expand the golden dataset with French-language cases and additional edge cases (ambiguous activity, partial addresses, multi-location submissions).
3. Persist extraction and evaluation results in PostgreSQL instead of flat JSON files to enable cross-project analytics with Project 2.
4. Add end-to-end integration tests that exercise the full `X-Correlation-ID` trace from this service through the Underwriting Agent.
5. Introduce a per-request cost and retry budget in `config.py`, with explicit rejection when limits are exceeded.
6. Formalize a versioned prompt-change process (changelog per prompt version) for `prompts/extraction_prompt.py`.

## Agentic AI Best Practices Applied Here

- **Single-responsibility agent**: this service only extracts and validates; it never makes underwriting or pricing decisions, keeping the agent boundary clean and auditable.
- **Deterministic guardrails around generative output**: every LLM response passes through Pydantic validation, normalization, and business rules before being trusted downstream.
- **Explicit escalation signal**: `review_required` gives a clear, inspectable handoff point to a human reviewer rather than a silent LLM decision.
- **Provider abstraction as a resilience pattern**: the `LLMClient` protocol allows failover or A/B testing between Gemini and Groq without touching business logic.
- **Correlation-first design**: propagating `X-Correlation-ID` across services is a foundational practice for auditing multi-agent workflows end to end.
- **Next-level practice to adopt**: expose this extractor as an MCP-compatible tool so the Underwriting Agent (or any future orchestrator) can call it through a standardized tool contract instead of a bespoke HTTP client, improving interoperability across the platform.
