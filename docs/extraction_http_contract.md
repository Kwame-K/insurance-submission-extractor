# Extraction HTTP Contract — v1

## Purpose

This contract defines the boundary between the insurance submission extraction
service and a downstream consumer, such as an underwriting workflow.

The extraction service:

- Reads broker emails, free text, forms, or text extracted from PDF documents.
- Returns candidate structured data, missing fields, quality flags, and routing signals.
- Does not accept, decline, price, bind, or otherwise make underwriting decisions.

The consumer:

- Generates and owns the `source_id`.
- Validates `submission_data` against its own canonical domain model.
- Decides the next business action.
- Persists submissions, decisions, and audit records.

## Endpoints

```text
GET /health
POST /v1/extract-submission
```

GET /health  verifies that the API process is available. It does not call an LLM provider.
POST /v1/extract-submission  extracts candidate information from one text-based
insurance source.


Request
Request body
{
  "source_id": "SRC-BROKER-EMAIL-001",
  "source_type": "BROKER_EMAIL",
  "document_name": "northwind-quote-request.txt",
  "content": "Please quote commercial property insurance for our restaurant in Montreal.",
  "language": "en"
}

| Field         | Type           | Required | Description                                                      |
| ------------- | -------------- | -------- | ---------------------------------------------------------------- |
| source_id     | string         | Yes      | Consumer-generated identifier, unique within the consumer system |
| source_type   | enum           | Yes      | BROKER_EMAIL , PDF_TEXT , FREE_TEXT , or FORM                    |
| document_name | string or null | No       | Original source document name                                    |
| content       | string         | Yes      | Raw text to be extracted                                         |
| language      | string         | No       | Source language, defaults to en                                  |

Binary uploads are outside the scope of v1. A PDF must be converted to text by
the caller or by a future ingestion service.
Successful response
A successful response returns HTTP  200 .

{
  "source_id": "SRC-MANUAL-002",
  "extraction_status": "COMPLETE",
  "submission_data": {
    "submission_id": "SRC-MANUAL-002",
    "product_line": "commercial_property",
    "insured_name": null,
    "business_activity": "restaurant",
    "location_city": "Montreal",
    "location_province": "QC",
    "postal_code": "H2X 1Y4",
    "building_construction_year": 1998,
    "occupancy_type": "restaurant",
    "employee_count": 24,
    "annual_revenue_cad": 1200000,
    "requested_coverages": [
      "property_damage",
      "business_interruption"
    ],
    "claims_history": [],
    "claims_history_status": "no_losses_reported",
    "source_language": "en"
  },
  "missing_fields": [],
  "ambiguous_fields": [],
  "field_confidence": {},
  "source_references": [],
  "data_quality_flags": [],
  "review_required": false,
  "provider": "groq",
  "model": "openai/gpt-oss-120b",
  "processed_at": "2026-09-15T03:45:54.044894Z",
  "extraction_notes": [],
  "error_code": null,
  "error_message": null
}


Response fields

| Field              | Description                                             |
| ------------------ | ------------------------------------------------------- |
| source_id          | Identifier supplied in the request                      |
| extraction_status  | COMPLETE , PARTIAL , or FAILED                          |
| submission_data    | Candidate data only; it is not an underwriting decision |
| missing_fields     | Required fields not present in the source               |
| ambiguous_fields   | Fields that require clarification                       |
| field_confidence   | Optional confidence values between 0 and 1              |
| source_references  | Optional source evidence for extracted fields           |
| data_quality_flags | Deterministic validation findings                       |
| review_required    | Routing signal for consumer review workflow             |
| provider           | LLM provider used for the extraction                    |
| model              | LLM model used for the extraction                       |
| processed_at       | UTC timestamp of extraction completion                  |
| extraction_notes   | Additional extraction notes                             |
| error_code         | Machine-readable error code, if applicable              |
| error_message      | Human-readable error message, if applicable             |


COMPLETE  means the service found no required missing fields. It does not prove
that the submission is eligible, priced, accepted, or free from underwriting risk.
 PARTIAL  means the extraction completed but required information is missing.
Errors
Invalid request
An invalid request returns HTTP  422 . This includes an empty  content , an
unsupported  source_type , or fields not defined by the contract.
Provider failure
If the selected LLM provider cannot complete the request, the service returns
HTTP  502 .

{
  "detail": {
    "source_id": "SRC-BROKER-EMAIL-001",
    "error_code": "LLM_PROVIDER_ERROR",
    "error_message": "Provider is unavailable."
  }
}
Consumer responsibilities
The consumer must:
•	Treat  submission_data  as candidate information.
•	Apply its own canonical validation before persistence or underwriting.
•	Route any response with  review_required: true  to an appropriate review workflow.
•	Store provider, model, timestamp, source identifier, and contract version for audit.
•	Avoid treating  COMPLETE  as a policy, pricing, eligibility, or binding decision.



## Correlation ID

The consumer should generate an `X-Correlation-ID` header for every request.

The service returns the same value in the `X-Correlation-ID` response header.
If the header is omitted, the service generates a UUID and returns it.

The consumer must propagate the same correlation identifier when it calls
downstream services. This enables end-to-end tracing across Project 1,
Project 3, and Project 4.
