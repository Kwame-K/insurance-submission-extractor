"""Deterministic field-level evidence: find the source passage supporting each value.

This never asks a model. A value that no passage supports is reported as
unsupported so a reviewer can check it. The search is intentionally lenient
(accent- and case-insensitive, flexible number formats), so it favors missing a
hallucination over raising false alarms.
"""

from __future__ import annotations

import re
import unicodedata
from collections.abc import Callable

from insurance_submission_extractor.schemas.submission import (
    CoverageType,
    FieldEvidence,
    InsuranceSubmission,
    ProductLine,
)

MAX_EXCERPT_LENGTH = 240
_SEP = r"[,.\s\u00a0\u202f]?"

PROVINCE_NAMES = {
    "QC": ("quebec",),
    "ON": ("ontario",),
    "BC": ("british columbia", "colombie-britannique"),
    "AB": ("alberta",),
    "MB": ("manitoba",),
    "SK": ("saskatchewan",),
    "NB": ("new brunswick", "nouveau-brunswick"),
    "NS": ("nova scotia", "nouvelle-ecosse"),
    "PE": ("prince edward island", "ile-du-prince-edouard"),
    "NL": ("newfoundland", "terre-neuve"),
    "YT": ("yukon",),
    "NT": ("northwest territories", "territoires du nord-ouest"),
    "NU": ("nunavut",),
}

_REVENUE_WORDS = re.compile(r"revenue|revenu|sales|ventes|chiffre d'affaires|turnover")
_EMPLOYEE_WORDS = re.compile(r"employ|staff|personnel|full-time|workers|salari")
_BUILD_WORDS = re.compile(
    r"built|constructed|construction|construit|batiment|bati\b|year built|erected"
)
_CLAIM_WORDS = re.compile(
    r"claim|loss|sinistre|incident|reclamation|perte|theft|fire|flood|water damage|"
    r"incendie|vol\b|degat|breach"
)

_COVERAGE_PATTERNS: dict[CoverageType, re.Pattern[str]] = {
    CoverageType.PROPERTY_DAMAGE: re.compile(
        r"property|building and contents|dommages aux biens|biens commerciaux|"
        r"couverture des biens"
    ),
    CoverageType.BUSINESS_INTERRUPTION: re.compile(
        r"business interruption|interruption des affaires|perte d'exploitation"
    ),
    CoverageType.GENERAL_LIABILITY: re.compile(
        r"general liability|responsabilite civile|liability"
    ),
    CoverageType.CYBER_LIABILITY: re.compile(r"cyber"),
    CoverageType.EQUIPMENT_BREAKDOWN: re.compile(
        r"equipment breakdown|bris d'equipement|bris de machine"
    ),
    CoverageType.CRIME: re.compile(r"crime|fraud|fraude"),
}

_PRODUCT_PATTERNS: dict[ProductLine, re.Pattern[str]] = {
    ProductLine.COMMERCIAL_PROPERTY: re.compile(r"property|biens commerciaux|assurance des biens"),
    ProductLine.CYBER: re.compile(r"cyber"),
    ProductLine.COMMERCIAL_GENERAL_LIABILITY: re.compile(
        r"general liability|responsabilite civile|\bcgl\b"
    ),
    ProductLine.BUSINESS_PACKAGE: re.compile(r"package|multirisque|\bbop\b"),
}


def _fold(text: str) -> str:
    decomposed = unicodedata.normalize("NFKD", text)
    stripped = "".join(char for char in decomposed if not unicodedata.combining(char))

    return stripped.casefold().replace("\u2019", "'")


class _Unit:
    """One sentence or form line, kept with an accent-folded copy for matching."""

    def __init__(self, original: str) -> None:
        self.original = original.strip()
        self.folded = _fold(self.original)

    @property
    def excerpt(self) -> str:
        text = " ".join(self.original.split())

        return text if len(text) <= MAX_EXCERPT_LENGTH else text[: MAX_EXCERPT_LENGTH - 1] + "…"


def _split_units(text: str) -> list[_Unit]:
    units: list[_Unit] = []

    for line in text.splitlines():
        for sentence in re.split(r"(?<=[.!?])\s+", line):
            if sentence.strip():
                units.append(_Unit(sentence))

    return units


def _first(units: list[_Unit], predicate: Callable[[_Unit], bool]) -> _Unit | None:
    return next((unit for unit in units if predicate(unit)), None)


def _integer_pattern(value: int) -> re.Pattern[str]:
    digits = str(value)
    groups: list[str] = []

    while digits:
        groups.insert(0, digits[-3:])
        digits = digits[:-3]

    return re.compile(r"(?<!\d)" + _SEP.join(groups) + r"(?!\d)")


def _amount_patterns(value: float) -> list[re.Pattern[str]]:
    amount = int(value)
    patterns = [_integer_pattern(amount)]

    if amount >= 1_000_000 and amount % 100_000 == 0:
        millions = f"{amount / 1_000_000:g}".replace(".", "[.,]")
        patterns.append(re.compile(r"(?<!\d)" + millions + r"\s?(?:m\b|million)"))

    if amount >= 1_000 and amount % 1_000 == 0:
        patterns.append(re.compile(r"(?<!\d)" + str(amount // 1_000) + r"\s?k\b"))

    return patterns


def _evidence_name(units: list[_Unit], value: str) -> _Unit | None:
    needle = _fold(value).strip()

    return _first(units, lambda unit: needle in unit.folded)


def _evidence_activity(units: list[_Unit], value: str) -> _Unit | None:
    needle = _fold(value).strip()
    exact = _first(units, lambda unit: needle in unit.folded)

    if exact is not None:
        return exact

    tokens = [token for token in re.findall(r"\w+", needle) if len(token) >= 4]

    return _first(units, lambda unit: any(token in unit.folded for token in tokens))


def _evidence_province(units: list[_Unit], code: str) -> _Unit | None:
    names = PROVINCE_NAMES.get(code.upper(), ())
    code_pattern = re.compile(rf"(?<![A-Za-z]){re.escape(code.upper())}(?![A-Za-z])")

    return _first(
        units,
        lambda unit: (
            bool(code_pattern.search(unit.original)) or any(name in unit.folded for name in names)
        ),
    )


def _evidence_postal_code(units: list[_Unit], value: str) -> _Unit | None:
    target = re.sub(r"[\s-]", "", value).casefold()

    return _first(
        units,
        lambda unit: target in re.sub(r"[\s-]", "", unit.folded),
    )


def _evidence_year(units: list[_Unit], year: int) -> _Unit | None:
    pattern = _integer_pattern(year)

    return _first(
        units,
        lambda unit: bool(pattern.search(unit.folded)) and bool(_BUILD_WORDS.search(unit.folded)),
    )


def _evidence_employees(units: list[_Unit], count: int) -> _Unit | None:
    if count == 0:
        zero = re.compile(
            r"no employees|aucun employe|sans employe|0 employ|employees:\s*0|employes:\s*0|"
            r"works alone|travaille seul|sole"
        )
        return _first(units, lambda unit: bool(zero.search(unit.folded)))

    pattern = _integer_pattern(count)

    return _first(
        units,
        lambda unit: (
            bool(pattern.search(unit.folded)) and bool(_EMPLOYEE_WORDS.search(unit.folded))
        ),
    )


def _evidence_revenue(units: list[_Unit], amount: float) -> _Unit | None:
    if int(amount) == 0:
        zero = re.compile(r"(?<![\d.,])0(?![\d])|no revenue|sans revenu|aucun revenu|not generated")
        return _first(
            units,
            lambda unit: (
                bool(_REVENUE_WORDS.search(unit.folded)) and bool(zero.search(unit.folded))
            ),
        )

    patterns = _amount_patterns(amount)

    return _first(
        units,
        lambda unit: (
            bool(_REVENUE_WORDS.search(unit.folded))
            and any(pattern.search(unit.folded) for pattern in patterns)
        ),
    )


def _evidence_claim_year(units: list[_Unit], year: int) -> _Unit | None:
    pattern = _integer_pattern(year)

    return _first(
        units,
        lambda unit: bool(pattern.search(unit.folded)) and bool(_CLAIM_WORDS.search(unit.folded)),
    )


def find_field_evidence(
    submission_text: str,
    submission: InsuranceSubmission,
) -> tuple[list[FieldEvidence], list[str]]:
    """Return (supporting passages, fields whose value no passage supports)."""
    units = _split_units(submission_text)
    references: list[FieldEvidence] = []
    unsupported: list[str] = []

    def record(field_name: str, unit: _Unit | None) -> None:
        if unit is None:
            if field_name not in unsupported:
                unsupported.append(field_name)
            return
        references.append(FieldEvidence(field_name=field_name, source_excerpt=unit.excerpt))

    if submission.product_line not in (None, ProductLine.OTHER):
        pattern = _PRODUCT_PATTERNS[submission.product_line]
        record("product_line", _first(units, lambda unit: bool(pattern.search(unit.folded))))

    if submission.insured_name:
        record("insured_name", _evidence_name(units, submission.insured_name))

    if submission.business_activity:
        record("business_activity", _evidence_activity(units, submission.business_activity))

    if submission.location_city:
        record("location_city", _evidence_name(units, submission.location_city))

    if submission.location_province:
        record("location_province", _evidence_province(units, submission.location_province))

    if submission.postal_code:
        record("postal_code", _evidence_postal_code(units, submission.postal_code))

    if submission.building_construction_year is not None:
        record(
            "building_construction_year",
            _evidence_year(units, submission.building_construction_year),
        )

    if submission.employee_count is not None:
        record("employee_count", _evidence_employees(units, submission.employee_count))

    if submission.annual_revenue_cad is not None:
        record("annual_revenue_cad", _evidence_revenue(units, submission.annual_revenue_cad))

    for coverage in submission.requested_coverages:
        pattern = _COVERAGE_PATTERNS.get(coverage)
        if pattern is not None:
            record(
                "requested_coverages", _first(units, lambda u, p=pattern: bool(p.search(u.folded)))
            )

    for claim in submission.claims_history:
        record("claims_history", _evidence_claim_year(units, claim.year))

    return references, unsupported
