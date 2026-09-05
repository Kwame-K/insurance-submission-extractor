# System Architecture

## Purpose

This document describes the architecture of the Insurance Submission Extractor.

The application transforms unstructured commercial insurance submissions into structured, validated, and auditable data. It is designed as a provider-agnostic extraction component that can later become the ingestion and validation layer of an agentic underwriting platform.

## High-Level Architecture

```mermaid
flowchart TD
    A[Broker Submission<br/>Plain Text] --> B[CLI]
    B --> C[SubmissionExtractor]

    C --> D[LLM Factory]
    D --> E[GeminiClient<br/>gemini-3.7-flash]
    D --> F[GroqClient<br/>openai/gpt-oss-120b]

    E --> G[Structured JSON Output]
    F --> G

    G --> H[Pydantic Schema Validation]
    H --> I[Deterministic Domain Normalization]
    I --> J[Deterministic Business Validation]
    J --> K[ExtractionResult]

    K --> L[Missing Fields]
    K --> M[Data Quality Flags]
    K --> N[Review Required]
    K --> O[Validated Submission Data]
```

## Main Components

| Component | Responsibility | Provider-Specific |
|---|---|---:|
| `cli.py` | Accepts a text submission or input file and prints a JSON result | No |
| `config.py` | Loads validated runtime configuration from environment variables | No |
| `llm/base.py` | Defines the common LLM client contract | No |
| `llm/factory.py` | Creates the client selected by `LLM_PROVIDER` | No |
| `llm/gemini_client.py` | Calls Gemini and parses structured output | Yes |
| `llm/groq_client.py` | Calls Groq and parses structured output | Yes |
| `schemas/submission.py` | Defines Pydantic contracts and domain enums | No |
| `services/extractor.py` | Coordinates extraction, normalization, and validation | No |
| `services/normalizers.py` | Applies deterministic domain mappings | No |
| `services/validators.py` | Identifies missing fields and business-rule issues | No |
| `evaluation.py` | Compares results against the golden dataset | No |
| `scripts/run_evaluation.py` | Runs provider-specific benchmark evaluations | No |

## Extraction Sequence

```mermaid
sequenceDiagram
    actor Broker
    participant CLI
    participant Extractor as SubmissionExtractor
    participant Provider as LLM Provider
    participant Schema as Pydantic
    participant Normalizer
    participant Validator

    Broker->>CLI: Submit unstructured insurance text
    CLI->>Extractor: extract(submission_text, submission_id)
    Extractor->>Provider: Request structured extraction
    Provider-->>Extractor: JSON response
    Extractor->>Schema: Validate JSON against InsuranceSubmission
    Schema-->>Extractor: Validated submission object
    Extractor->>Normalizer: normalize_submission(submission)
    Normalizer-->>Extractor: Normalized submission
    Extractor->>Validator: validate_submission(submission)
    Validator-->>Extractor: ValidationReport
    Extractor-->>CLI: ExtractionResult
    CLI-->>Broker: JSON result
```

## Validation Layers

The application applies four distinct control layers. Each layer addresses a different risk and must remain separate.

| Layer | Purpose | Example |
|---|---|---|
| LLM structured extraction | Convert unstructured text into a known JSON shape | Extract annual revenue from a broker submission |
| Pydantic validation | Enforce types, enums, numeric constraints, and internal model consistency | Reject a future claim year or an unsupported claim type |
| Deterministic normalization | Apply explicit and versioned domain mappings | Map business activity `Restaurant` to occupancy type `restaurant` |
| Deterministic business validation | Identify missing or inconsistent underwriting information | Flag a building construction year later than a reported claim year |

## Provider Abstraction

```mermaid
classDiagram
    class LLMClient {
        <<Protocol>>
        +provider: str
        +model: str
        +extract_submission(submission_text, submission_id) InsuranceSubmission
    }

    class GeminiClient {
        +provider: str
        +model: str
        +extract_submission(submission_text, submission_id) InsuranceSubmission
    }

    class GroqClient {
        +provider: str
        +model: str
        +extract_submission(submission_text, submission_id) InsuranceSubmission
    }

    class SubmissionExtractor {
        +extract(submission_text, submission_id) ExtractionResult
    }

    LLMClient <|.. GeminiClient
    LLMClient <|.. GroqClient
    SubmissionExtractor --> LLMClient
```

The application business layer depends on the `LLMClient` contract, not on a provider SDK. This allows Gemini and Groq to be selected through environment configuration without changing schemas, validation rules, normalization logic, CLI behavior, or evaluation code.

## Evaluation Architecture

```mermaid
flowchart LR
    A[JSONL Golden Dataset] --> B[Evaluation Runner]
    B --> C{Selected Provider}
    C --> D[Gemini]
    C --> E[Groq]
    D --> F[SubmissionExtractor]
    E --> F
    F --> G[ExtractionResult]
    G --> H[Field Comparison]
    G --> I[Missing Field Comparison]
    G --> J[Flag Comparison]
    G --> K[Review Routing Comparison]
    H --> L[Timestamped JSON Report]
    I --> L
    J --> L
    K --> L
```

The evaluation runner measures provider behavior against a versioned synthetic golden dataset. It evaluates expected fields, acceptable semantic alternatives, expected missing fields, deterministic data-quality flags, and the `review_required` routing signal.

## Security Boundaries

```text
Tracked by Git
- Source code
- Tests
- Synthetic submissions
- Golden dataset
- Documentation
- .env.example
- uv.lock

Never tracked by Git
- .env
- API keys
- Real customer submissions
- Real claims data
- Generated evaluation reports
```

All current examples and datasets are synthetic. The application must not send real policyholder or claims data to external LLM providers without a documented data-governance, privacy, contractual, and security review.

## Future Underwriting Agent

The current component will become the first stage of a larger LangGraph underwriting workflow.

```mermaid
flowchart TD
    A[Submission Intake] --> B[Extraction and Validation]
    B --> C{Submission Complete?}
    C -- No --> D[Request Missing Information]
    C -- Yes --> E[Retrieve Underwriting Rules]
    E --> F[Claims and Exposure Analysis]
    F --> G[Pricing Model]
    G --> H[Risk and Anomaly Detection]
    H --> I[Recommendation Generation]
    I --> J{Human Review Required?}
    J -- Yes --> K[Underwriter Review]
    J -- No --> L[Underwriting Report]
    K --> L
```

The Insurance Submission Extractor is intentionally limited to intake, normalization, and validation. It does not make underwriting decisions or pricing recommendations.
