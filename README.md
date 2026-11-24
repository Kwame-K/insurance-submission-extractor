# Insurance Submission Extractor

[![Continuous Integration](../../actions/workflows/ci.yml/badge.svg)](../../actions/workflows/ci.yml)

A provider-agnostic LLM application that converts unstructured commercial insurance submission text into validated, structured data.

This repository is Project 1 in the Insurance Agentic Platform. It owns extraction, normalization, source evidence, and data-quality validation. It does not make underwriting decisions, calculate premiums, or bind coverage.

> This is a portfolio and learning project. The examples and evaluation data are synthetic.

## Problem

Broker submissions often arrive as emails, documents, or free-text forms. The extractor takes the text of a submission and turns it into candidate insurance fields: product line, requested coverages, insured name, business activity, location, building characteristics, employee count, revenue, and claims history. It reports missing or ambiguous information instead of treating the model output as a verified submission.

The input contract is text-based. This service does not read PDF attachments or perform OCR.

## Key Features

- Gemini and Groq implementations behind a shared LLM client interface.
- Structured extraction validated with Pydantic.
- Deterministic normalization, business-rule validation, and source-evidence checks.
- Separate representations for missing claims history and explicitly reported no-loss history.
- `source_references` for supported values, `ambiguous_fields` for unsupported values, and a `review_required` routing signal.
- Optional provider fallback for provider failures and selected explicit fields that the primary response omitted.
- CLI, FastAPI, and an MCP stdio server; HTTP and MCP share the v1 response contract.
- Structured extraction logs and optional SQLite or PostgreSQL history.
- Versioned synthetic evaluation datasets and a multi-provider regression runner.

## Architecture

```text
Submission text
    ↓
CLI / FastAPI / MCP
    ↓
SubmissionExtractor → Gemini or Groq
    ↓
Pydantic validation
    ↓
Deterministic normalization, business validation, and source evidence checks
    ↓
Extraction result + missing fields + review signal
    ↓
HTTP/MCP consumer or evaluation runner
```

See [System Architecture](docs/architecture/system-architecture.md) and the [HTTP extraction contract](docs/extraction_http_contract.md).

## Project Structure

```text
insurance-submission-extractor/
├── data/
│   ├── golden/                 # Versioned synthetic JSONL cases
│   ├── evaluations/            # Evaluation reports
│   └── synthetic/              # Example and generated submissions
├── docs/
│   ├── architecture/
│   └── extraction_http_contract.md
├── scripts/
│   ├── generate_golden_dataset.py
│   ├── run_evaluation.py
│   └── summarize_logs.py
├── src/insurance_submission_extractor/
│   ├── api/
│   ├── llm/
│   ├── mcp_server/
│   ├── prompts/
│   ├── schemas/
│   ├── services/
│   ├── cli.py
│   ├── config.py
│   └── evaluation.py
├── tests/
├── .env.example
├── alembic.ini
├── compose.yaml
├── Dockerfile
├── pyproject.toml
└── uv.lock
```

## Technology Stack

Python 3.11+, uv, FastAPI, Pydantic, Gemini, Groq, SQLAlchemy, Alembic, pytest, Ruff, Docker, and GitHub Actions.

## Setup

```bash
git clone [https://github.com/Kwame-K/insurance-submission-extractor.git](https://github.com/Kwame-K/insurance-submission-extractor.git)
cd insurance-submission-extractor
uv sync --all-groups
cp .env.example .env
```

Configure the provider you intend to use:

```dotenv
LLM_PROVIDER=groq
GROQ_API_KEY=your_groq_api_key
GROQ_MODEL=openai/gpt-oss-120b
GROQ_MAX_RETRIES=3
```

For Gemini, set `LLM_PROVIDER=gemini`, `GEMINI_API_KEY`, and `GEMINI_MODEL=gemini-3.7-flash`. Configure both providers only if you want to switch between them or enable fallback. Do not commit `.env` or API keys.

### Database Persistence

Database persistence is optional. Set `DATABASE_URL` to a SQLite or PostgreSQL connection string:

```dotenv
DATABASE_URL=sqlite:///logs/history.db
```

Extraction history stores identifiers, provider and model, latency, fallback and review flags, token counts, estimated cost, and the names of unsupported fields. It does not store submission text, extracted values, or evidence excerpts. Evaluation history can store run metrics and per-case outcomes.

Alembic migrations run automatically on the first database write by default. To manage them explicitly, set `DATABASE_AUTO_MIGRATE=false` and run:

```bash
uv run alembic -c alembic.ini upgrade head
```

A database write failure is logged and does not fail the extraction. JSONL logging remains available independently.

## Usage

### CLI

```bash
uv run insurance-submission-extractor \
  --input-file data/synthetic/restaurant_submission.txt \
  --submission-id SUB-2026-0001
```

### Validation Strategy

1. Pydantic validates types, constraints, and enumerated values.
2. Deterministic normalization can derive occupancy from business activity without replacing explicit occupancy information.
3. Business validation checks for missing fields and inconsistencies, such as an unrecognized province, duplicate claims, or a construction year later than a reported claim year.
4. The source-evidence check looks for supporting text. Unsupported values are reported in `ambiguous_fields`, receive a `VALUE_NOT_FOUND_IN_SOURCE` flag, and set `review_required=true`.

The evidence check does not verify `claims_history_status`, `source_language`, or `occupancy_type`. Finding matching words is not proof that a field was interpreted correctly.

### Provider Fallback

Set `LLM_FALLBACK_PROVIDER` to enable fallback. It can run after a provider error or when the primary response omits explicit source text for revenue, employee count, construction year, postal code, or a named property or business interruption coverage. It does not infer values. When fallback is used, the extraction is routed to review even if the fallback supplies the missing value.

## HTTP API

```bash
uv run uvicorn insurance_submission_extractor.api.app:app --reload
```

| Method | Path | Purpose |
|---|---|---|
| GET | `/health` | Check API liveness |
| POST | `/v1/extract-submission` | Extract and validate information from submission text |
| GET | `/docs` | Browse the OpenAPI contract |

The API runs on port `8000` by default. Send `X-Correlation-ID` to trace a request across services; the API returns it in the response and generates one when omitted. See the [HTTP extraction contract](docs/extraction_http_contract.md) for request and response details.

The Underwriting Agent calls this API from `POST /extract-and-underwrite`. It maps the candidate extraction to its own submission model and handles any missing underwriting fields downstream. The extractor itself does not approve or decline a submission.

## Observability

The `insurance_submission_extractor.extraction` logger emits structured metadata for each extraction. Set `EXTRACTION_LOG_PATH` to also append records to a local JSONL file.

```bash
uv run python scripts/summarize_logs.py logs/extractions.jsonl
```

The summary covers latency, error and fallback rates, review rate, unsupported fields, provider calls, tokens, and estimated cost when pricing is configured. Provider SDK retries are not included in the application call counts. Failed attempts that do not return usage cannot be priced.

With `DATABASE_URL` configured, run `uv run python scripts/summarize_logs.py` without a log path to summarize database history; add `--evaluations` to list stored evaluation runs.

## MCP Server

```bash
uv run insurance-submission-mcp
```

The stdio server exposes `extract_submission`. It accepts `source_id`, `content`, and optional `language`, `source_type`, and `document_name`. It returns the shared v1 extraction contract and is annotated as read-only and idempotent. Logs go to stderr.

```bash
npx @modelcontextprotocol/inspector uv run insurance-submission-mcp
```

## Docker

```bash
docker compose up --build -d
curl -i -H "X-Correlation-ID: docker-health-001" http://127.0.0.1:8000/health
docker compose down
```

The central [Insurance Agentic Platform](https://github.com/Kwame-K/insurance-agentic-platform) runs this repository as `submission-extractor` on port `8000`, with PostgreSQL configured through `DATABASE_URL`.

## Evaluation

```bash
uv run python scripts/run_evaluation.py --provider gemini
uv run python scripts/run_evaluation.py --provider groq
```

Use the expanded v2 dataset explicitly:

```bash
uv run python scripts/run_evaluation.py --provider gemini \
  --dataset data/golden/insurance_submission_cases_v2.jsonl \
  --delay-seconds 1
```

The v2 dataset contains 97 synthetic cases: four hand-written cases and 93 generated cases, including coverage-phrasing regressions and 24 edge cases. Evaluation reports are written to `data/evaluations/`.

| Recorded run | Cases | System | Passed |
|---|---:|---|---:|
| Original baseline, three runs | 4 | Gemini | 11/12 |
| Original baseline, three runs | 4 | Groq | 12/12 |
| 2026-10-05 baseline, three runs | 67 | Gemini | 199/201 |
| 2026-10-05 baseline, three runs | 67 | Groq | 179/201 |
| After coverage prompt fix | 73 | Gemini | 73/73 |
| Edge-case expansion, run 1 | 97 | Gemini | 97/97 |
| Edge-case expansion, run 2 | 97 | Gemini | 96/97 |
| Edge-case expansion | 97 | Gemini + Groq fallback | 97/97; fallback not used |

The 96/97 run included a transient provider error. In a separate simulated Gemini outage, Groq returned the expected field values on 14/14 cases, but the harness marked those cases as failures because fallback sets `review_required=true` by design. These are regression results on synthetic data, not estimates of real-world accuracy. See the [evaluation baseline](docs/architecture/evaluation-baseline.md).

## Quality Checks

```bash
uv run ruff format --check .
uv run ruff check .
uv run pytest
```

## Limitations

- The input is submission text, not a PDF, scanned document, or raw attachment.
- The synthetic dataset was developed alongside the prompt. Multi-site examples exercise a single-location schema, not multi-location extraction.
- `review_required` is a routing signal, not a human approval workflow owned by this service.
- The fallback omission check covers selected fields only. It does not detect every wrong product line, insured name, or province.
- Evaluation scores do not establish production accuracy or suitability for real underwriting.

## Position in the Insurance Agentic Platform

| Project | Responsibility |
|---|---|
| Submission Extractor (this repo) | Candidate data extraction and validation |
| [Data Analyst Agent](https://github.com/Kwame-K/insurance-data-analyst-agent) | Controlled portfolio analytics |
| [Insurance Knowledge Agent](https://github.com/Kwame-K/insurance-rag-assistant) | Documentary evidence retrieval |
| [Underwriting Agent](https://github.com/Kwame-K/underwriting-agent) | Deterministic underwriting and review workflow |
| [Insurance Agentic Platform](https://github.com/Kwame-K/insurance-agentic-platform) | Local Docker Compose orchestration |

## Improvements and Next Steps

- Expand the regression corpus and make fallback expectations explicit in the evaluation harness.
- Extend tracing for latency, cost, and provider attempts.
- Strengthen automated checks of correlation IDs, extraction mapping, and review routing across services.
- Keep extraction history and evaluation reporting separate from downstream underwriting decisions.


## Agentic AI Best Practices Applied Here

- **Single-responsibility agent**: this service only extracts and validates; it never makes underwriting or pricing decisions, keeping the agent boundary clean and auditable.
- **Deterministic guardrails around generative output**: every LLM response passes through Pydantic validation, normalization, and business rules before being trusted downstream.
- **Explicit escalation signal**: `review_required` gives a clear, inspectable handoff point to a human reviewer rather than a silent LLM decision.
- **Provider abstraction as a resilience pattern**: the `LLMClient` protocol allows failover or A/B testing between Gemini and Groq without touching business logic.
- **Correlation-first design**: propagating `X-Correlation-ID` across services is a foundational practice for auditing multi-agent workflows end to end.
- **Standardized tool contract**: the extractor is exposed as an MCP tool (`insurance-submission-mcp`) that reuses the HTTP v1 contract, so the Underwriting Agent or any orchestrator can call it without a bespoke HTTP client. Next step: add MCP integration tests with a real client session and an HTTP transport for remote deployment.

## Database persistence

Extraction and evaluation history can also be stored in a database. Persistence is off by default and works with SQLite or PostgreSQL through SQLAlchemy.

```bash
DATABASE_URL=sqlite:///logs/history.db
# or
DATABASE_URL=postgresql://user:password@localhost:5432/extractor
```

- **What is stored:** one row per extraction (identifiers, provider, model, latency, fallback, review flag, token counts, cost, names of unsupported fields) and, per evaluation run, the pass rates, field metrics and per-case outcomes. Submission text, extracted values and evidence excerpts are never stored.
- **JSONL logs still work:** the database is written in addition to `EXTRACTION_LOG_PATH`. A database failure only logs a warning and never fails an extraction.
- **Migrations:** schema changes are Alembic migrations shipped in the package. They are applied automatically on the first write; set `DATABASE_AUTO_MIGRATE=false` to manage them yourself with `uv run alembic -c alembic.ini upgrade head`.
- **Evaluation runs:** `scripts/run_evaluation.py` stores each run when `DATABASE_URL` or `--database-url` is set.
- **Reading history:** `uv run python scripts/summarize_logs.py` summarizes the database when no log file is given; add `--evaluations` to list stored evaluation runs.

Try PostgreSQL locally:

```bash
docker run --rm -d --name extractor-pg -e POSTGRES_PASSWORD=dev -e POSTGRES_DB=extractor -p 5432:5432 postgres:16
DATABASE_URL=postgresql://postgres:dev@localhost:5432/extractor uv run alembic -c alembic.ini upgrade head
```
