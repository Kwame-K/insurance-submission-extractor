from __future__ import annotations

from datetime import UTC, datetime
from enum import StrEnum
from typing import Annotated

from pydantic import BaseModel, Field, field_validator, model_validator


class ProductLine(StrEnum):
    COMMERCIAL_PROPERTY = "commercial_property"
    COMMERCIAL_GENERAL_LIABILITY = "commercial_general_liability"
    BUSINESS_PACKAGE = "business_package"
    CYBER = "cyber"
    OTHER = "other"


class CoverageType(StrEnum):
    PROPERTY_DAMAGE = "property_damage"
    BUSINESS_INTERRUPTION = "business_interruption"
    GENERAL_LIABILITY = "general_liability"
    CYBER_LIABILITY = "cyber_liability"
    EQUIPMENT_BREAKDOWN = "equipment_breakdown"
    CRIME = "crime"
    OTHER = "other"


class ClaimType(StrEnum):
    WATER_DAMAGE = "water_damage"
    FIRE = "fire"
    THEFT = "theft"
    LIABILITY = "liability"
    CYBER_INCIDENT = "cyber_incident"
    WEATHER = "weather"
    OTHER = "other"


class ClaimsHistoryStatus(StrEnum):
    NOT_PROVIDED = "not_provided"
    NO_LOSSES_REPORTED = "no_losses_reported"
    LOSSES_REPORTED = "losses_reported"


class DataQualitySeverity(StrEnum):
    INFO = "info"
    WARNING = "warning"
    ERROR = "error"


class DataQualityFlag(BaseModel):
    field: str
    severity: DataQualitySeverity
    code: str
    message: str


class ClaimRecord(BaseModel):
    year: Annotated[int, Field(ge=1900, le=2100)]
    claim_type: ClaimType
    amount_cad: Annotated[float, Field(ge=0)]
    description: str | None = None


class InsuranceSubmission(BaseModel):
    submission_id: str
    product_line: ProductLine | None = None
    insured_name: str | None = None
    business_activity: str | None = None
    location_city: str | None = None
    location_province: str | None = None
    postal_code: str | None = None
    building_construction_year: Annotated[int | None, Field(ge=1800, le=2100)] = None
    occupancy_type: str | None = None
    employee_count: Annotated[int | None, Field(ge=0)] = None
    annual_revenue_cad: Annotated[float | None, Field(ge=0)] = None
    requested_coverages: list[CoverageType] = Field(default_factory=list)
    claims_history: list[ClaimRecord] = Field(default_factory=list)
    claims_history_status: ClaimsHistoryStatus = ClaimsHistoryStatus.NOT_PROVIDED
    source_language: str = "en"

    @field_validator("location_province")
    @classmethod
    def normalize_province(cls, value: str | None) -> str | None:
        if value is None:
            return None

        normalized_value = value.strip().upper()
        province_mapping = {
            "QUEBEC": "QC",
            "QUÉBEC": "QC",
            "ONTARIO": "ON",
            "BRITISH COLUMBIA": "BC",
            "ALBERTA": "AB",
            "MANITOBA": "MB",
            "SASKATCHEWAN": "SK",
            "NEW BRUNSWICK": "NB",
            "NOVA SCOTIA": "NS",
            "PRINCE EDWARD ISLAND": "PE",
            "NEWFOUNDLAND AND LABRADOR": "NL",
        }

        return province_mapping.get(normalized_value, normalized_value)

    @model_validator(mode="after")
    def validate_claim_years(self) -> InsuranceSubmission:
        current_year = datetime.now(UTC).year

        for claim in self.claims_history:
            if claim.year > current_year:
                raise ValueError("Claim year cannot be in the future.")

        return self

    @model_validator(mode="after")
    def validate_claim_history(self) -> InsuranceSubmission:
        current_year = datetime.now(UTC).year

        for claim in self.claims_history:
            if claim.year > current_year:
                raise ValueError("Claim year cannot be in the future.")

        if self.claims_history_status == ClaimsHistoryStatus.NOT_PROVIDED and self.claims_history:
            self.claims_history_status = ClaimsHistoryStatus.LOSSES_REPORTED

        if (
            self.claims_history_status == ClaimsHistoryStatus.NO_LOSSES_REPORTED
            and self.claims_history
        ):
            raise ValueError("Claims history cannot contain records when no losses are reported.")

        return self


class ExtractionResult(BaseModel):
    submission: InsuranceSubmission
    missing_fields: list[str] = Field(default_factory=list)
    data_quality_flags: list[DataQualityFlag] = Field(default_factory=list)
    extraction_confidence: Annotated[float | None, Field(ge=0, le=1)] = None
    extraction_notes: list[str] = Field(default_factory=list)
    provider: str
    model: str
    processed_at: datetime = Field(default_factory=lambda: datetime.now(UTC))


class ValidationReport(BaseModel):
    missing_fields: list[str] = Field(default_factory=list)
    data_quality_flags: list[DataQualityFlag] = Field(default_factory=list)
    review_required: bool
