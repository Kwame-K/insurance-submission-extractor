"""Generate a deterministic synthetic golden dataset for extraction evaluation.

Ground truth is known by construction: each submission text is rendered from
a structured specification. Expected missing fields, quality flags and
``review_required`` are derived by running the deterministic domain rules on
the oracle submission, so the labels cannot drift from the validators.
"""

from __future__ import annotations

import argparse
import json
import random
import unicodedata
from pathlib import Path
from typing import Any

from insurance_submission_extractor.schemas.submission import (
    ClaimRecord,
    ClaimsHistoryStatus,
    ClaimType,
    CoverageType,
    InsuranceSubmission,
    ProductLine,
)
from insurance_submission_extractor.services import normalize_submission, validate_submission

SEED = 20261005
INPUT_PREFIX = "data/synthetic/generated"
BASE_DATASET = Path("data/golden/insurance_submission_cases.jsonl")
OUTPUT_DATASET = Path("data/golden/insurance_submission_cases_v2.jsonl")
OUTPUT_DIRECTORY = Path(INPUT_PREFIX)

POSTAL_LETTERS = "ABCEGHJKLMNPRSTVXY"
ALL_FIELDS = frozenset({"name", "province", "postal", "year", "employees", "revenue", "coverages"})

CITIES = [
    ("Montreal", "QC", "H", "Quebec"),
    ("Laval", "QC", "H", "Quebec"),
    ("Sherbrooke", "QC", "J", "Quebec"),
    ("Gatineau", "QC", "J", "Quebec"),
    ("Toronto", "ON", "M", "Ontario"),
    ("Ottawa", "ON", "K", "Ontario"),
    ("Calgary", "AB", "T", "Alberta"),
    ("Vancouver", "BC", "V", "British Columbia"),
    ("Winnipeg", "MB", "R", "Manitoba"),
    ("Halifax", "NS", "B", "Nova Scotia"),
]

# key: (english text, french text, acceptable extracted values, property-eligible)
ACTIVITIES = {
    "restaurant": ("restaurant", "restaurant", ["restaurant"], True),
    "retail": ("retail store", "magasin de détail", ["retail store", "small retail store"], True),
    "warehouse": ("warehouse", "entrepôt", ["warehouse"], True),
    "accounting": (
        "accounting firm",
        "cabinet comptable",
        ["accounting firm", "accounting"],
        False,
    ),
    "software": (
        "software development company",
        "entreprise de développement logiciel",
        ["software development company", "software development", "software company"],
        False,
    ),
    "law": ("law firm", "cabinet d'avocats", ["law firm", "legal services"], False),
    "dental": ("dental clinic", "clinique dentaire", ["dental clinic", "dental practice"], False),
    # Mixed activities: not in the random pools, used only by the ambiguous_activity family.
    "convenience_restaurant": (
        "restaurant and convenience store",
        "restaurant et dépanneur",
        [
            "restaurant and convenience store",
            "convenience store and restaurant",
            "convenience store/restaurant",
        ],
        True,
    ),
    "bakery_cafe": (
        "bakery and cafe",
        "boulangerie-café",
        ["bakery and cafe", "bakery and café", "bakery-cafe", "cafe and bakery", "café and bakery"],
        True,
    ),
}
PROPERTY_ACTIVITIES = ["restaurant", "retail", "warehouse"]
OTHER_ACTIVITIES = ["accounting", "software", "law", "dental"]

NAMES = {
    "restaurant": ["Maple Leaf Diner", "Brasserie du Vieux-Port", "Chez Marcel Bistro"],
    "retail": ["Harbourfront Hardware", "Boutique Beaulieu Ltée", "Cedar Row Gifts"],
    "warehouse": ["Northern Crate Logistics", "Westgate Storage Corp.", "Entrepôts Tremblay Inc."],
    "accounting": ["Lumen Accounting Services", "Cabinet Gagnon CPA", "Ledger & Oak LLP"],
    "software": ["Pixel Harbour Software", "Cedar Ridge Technologies", "Nordik Code Inc."],
    "law": ["Granite Peak Law LLP", "Fortin & Associés", "Bayview Legal Group"],
    "dental": ["Aurora Dental Group", "Clinique Dentaire Lavoie", "Maple Smiles Dental"],
    "convenience_restaurant": ["Dépanneur et Resto Chez Léo", "Corner Stop Grill & Market"],
    "bakery_cafe": ["Boulangerie Dupuis", "Golden Crust Bakery Cafe"],
}

# Used only by the edge-case families, so earlier random draws are unchanged.
ACCENTED_CITIES = [
    ("Montréal", "QC", "H", "Quebec"),
    ("Trois-Rivières", "QC", "G", "Quebec"),
    ("Saint-Jérôme", "QC", "J", "Quebec"),
]
STREETS = (
    ["1250 Sainte-Catherine Street West", "87 King Street East", "4410 Industrial Boulevard"],
    ["1250, rue Sainte-Catherine Ouest", "87, boulevard Saint-Laurent", "4410, avenue du Parc"],
)

PRODUCTS = {
    "commercial_property": ("commercial property insurance", "assurance des biens commerciaux"),
    "cyber": ("cyber insurance", "assurance cyber"),
    "commercial_general_liability": (
        "commercial general liability insurance",
        "assurance responsabilité civile générale",
    ),
    "business_package": ("business package insurance", "assurance multirisque commerciale"),
}

DEFAULT_COVERAGES = {
    "commercial_property": ["property_damage", "business_interruption"],
    "cyber": ["cyber_liability"],
    "commercial_general_liability": ["general_liability"],
    "business_package": ["property_damage", "business_interruption", "general_liability"],
}

COVERAGE_TEXT = {
    "property_damage": ("property damage", "dommages aux biens"),
    "business_interruption": ("business interruption", "interruption des affaires"),
    "general_liability": ("general liability", "responsabilité civile générale"),
    "cyber_liability": ("cyber liability", "responsabilité cyber"),
}

CLAIM_TEXT = {
    "water_damage": ("water damage", "dégât d'eau"),
    "fire": ("fire", "incendie"),
    "theft": ("theft", "vol"),
}

LABELS = {
    "en": {
        "title": "INSURANCE SUBMISSION FORM",
        "product": "Product",
        "name": "Insured",
        "activity": "Business activity",
        "location": "Location",
        "year": "Year built",
        "employees": "Employees",
        "revenue": "Annual revenue",
        "coverages": "Coverages requested",
        "claims": "Claims history",
        "na": "N/A",
        "none_claims": "None in the last 5 years",
    },
    "fr": {
        "title": "FORMULAIRE DE SOUMISSION D'ASSURANCE",
        "product": "Produit",
        "name": "Assuré",
        "activity": "Activité",
        "location": "Emplacement",
        "year": "Année de construction",
        "employees": "Employés",
        "revenue": "Revenus annuels",
        "coverages": "Garanties demandées",
        "claims": "Historique de sinistres",
        "na": "S.O.",
        "none_claims": "Aucun au cours des 5 dernières années",
    },
}


# (sentence, expected requested_coverages, language) - regression for dropped coverages
COVERAGE_PHRASINGS: list[tuple[str, tuple[str, ...], str]] = [
    (
        "We are seeking commercial property and business interruption coverage.",
        ("property_damage", "business_interruption"),
        "en",
    ),
    (
        "We are seeking business interruption and commercial property coverage.",
        ("business_interruption", "property_damage"),
        "en",
    ),
    (
        "We need property insurance together with business interruption insurance.",
        ("property_damage", "business_interruption"),
        "en",
    ),
    (
        "Please include building and contents coverage as well as business interruption.",
        ("property_damage", "business_interruption"),
        "en",
    ),
    (
        "We are looking for commercial property coverage only.",
        ("property_damage",),
        "en",
    ),
    (
        "Nous recherchons une couverture des dommages aux biens et de l'interruption des affaires.",
        ("property_damage", "business_interruption"),
        "fr",
    ),
]


def money(rng: random.Random, amount: float, lang: str, fmt: str | None = None) -> str:
    value = int(amount)
    if fmt is not None:
        millions = f"{value / 1_000_000:.1f}"
        return {
            "fr_m": millions.replace(".", ",") + " M$",
            "fr_millions": millions.replace(".", ",") + " millions de dollars",
            "fr_decimal": f"{value:,}".replace(",", " ") + ",00 $",
            "fr_k": f"{value // 1000} k$",
            "en_k": f"${value // 1000}K",
            "en_million": f"CAD {millions} million",
        }[fmt]
    if lang == "fr":
        return f"{value:,}".replace(",", " ") + " $"
    forms = [f"CAD {value:,}", f"${value:,}"]
    if value >= 1_000_000 and value % 100_000 == 0:
        forms.append(f"${value / 1_000_000:.1f}M")
    return rng.choice(forms)


def fold_accents(text: str) -> str:
    decomposed = unicodedata.normalize("NFKD", text)
    return "".join(char for char in decomposed if not unicodedata.combining(char))


def format_postal(postal: str, style: str) -> str:
    compact = postal.replace(" ", "")
    return {
        "standard": postal,
        "lower_compact": compact.lower(),
        "dashed": f"{compact[:3]}-{compact[3:]}",
        "no_space": compact,
    }[style]


def postal_code(rng: random.Random, first_letter: str) -> str:
    return (
        f"{first_letter}{rng.randint(0, 9)}{rng.choice(POSTAL_LETTERS)} "
        f"{rng.randint(0, 9)}{rng.choice(POSTAL_LETTERS)}{rng.randint(0, 9)}"
    )


def email_sentences(
    lang: str,
    parts: dict[str, Any],
) -> list[str]:
    """Return body sentences in a fixed order (shuffled later for noisy style)."""
    sentences: list[str] = []
    fr = lang == "fr"

    if parts["name"]:
        sentences.append(
            f"L'entreprise exerce ses activités sous le nom {parts['name']}."
            if fr
            else f"The business operates as {parts['name']}."
        )
    if parts["year"]:
        sentences.append(
            f"Le bâtiment a été construit en {parts['year']}."
            if fr
            else f"The building was constructed in {parts['year']}."
        )
    if parts["employees"] is not None:
        if parts["employees_n"] == 0:
            sentences.append(
                "Nous n'avons aucun employé; le propriétaire travaille seul."
                if fr
                else "We have no employees; the owner works alone."
            )
        else:
            sentences.append(
                f"Nous avons {parts['employees_n']} employés."
                if fr
                else f"We have {parts['employees_n']} employees."
            )
    if parts["revenue"] is not None:
        if parts["revenue_n"] == 0:
            sentences.append(
                "Il s'agit d'une jeune entreprise sans revenus à ce jour (revenus annuels : 0 $)."
                if fr
                else "This is a start-up with no revenue so far (annual revenue: $0)."
            )
        else:
            sentences.append(
                f"Les revenus annuels sont d'environ {parts['revenue']}."
                if fr
                else f"Annual revenue is approximately {parts['revenue']}."
            )
    if parts.get("coverage_sentence"):
        sentences.append(parts["coverage_sentence"])
    elif parts["coverages"]:
        joined = ", ".join(parts["coverages"])
        sentences.append(
            f"Garanties souhaitées : {joined}." if fr else f"Coverages needed: {joined}."
        )
    if parts.get("second_site"):
        sentences.append(parts["second_site"])
    for claim in parts["claims"]:
        sentences.append(
            f"En {claim['year']}, nous avons eu un sinistre ({claim['kind']}) d'environ "
            f"{claim['amount']}."
            if fr
            else f"In {claim['year']} we had a {claim['kind']} claim of about {claim['amount']}."
        )
    if parts["claims_none"]:
        sentences.append(
            "Nous n'avons eu aucun sinistre au cours des cinq dernières années."
            if fr
            else "We have had no losses or claims in the past five years."
        )
    return sentences


def render_text(
    rng: random.Random,
    style: str,
    lang: str,
    parts: dict[str, Any],
) -> str:
    labels = LABELS[lang]
    fr = lang == "fr"

    if style == "form":
        na = labels["na"]
        claims_value = na
        if parts["claims"]:
            claims_value = "; ".join(
                f"{c['year']} {c['kind']} ({c['amount']})" for c in parts["claims"]
            )
        elif parts["claims_none"]:
            claims_value = labels["none_claims"]
        rows = [
            (labels["product"], parts["product"]),
            (labels["name"], parts["name"] or na),
            (labels["activity"], parts["activity"]),
            (labels["location"], parts["location"]),
            (labels["year"], parts["year"] or na),
            (labels["employees"], na if parts["employees"] is None else parts["employees_n"]),
            (labels["revenue"], parts["revenue"] if parts["revenue"] is not None else na),
            (labels["coverages"], "; ".join(parts["coverages"]) or na),
            (labels["claims"], claims_value),
        ]
        if parts.get("second_site"):
            second_label = "Deuxième site" if fr else "Second location"
            rows.insert(4, (second_label, parts["second_site_form"]))
        return labels["title"] + "\n\n" + "\n".join(f"{k}: {v}" for k, v in rows) + "\n"

    body = email_sentences(lang, parts)
    if style == "noisy":
        rng.shuffle(body)
        body.extend(
            [
                "Notre référence : BRK-2019-4471." if fr else "Our reference: BRK-2019-4471.",
                "Vous pouvez me joindre au 514-555-0187."
                if fr
                else "You can reach me at 514-555-0187.",
                "L'entreprise existe depuis 1987."
                if fr
                else "The company has been in business since 1987.",
            ]
        )

    place = parts.get("location_in") or (
        f"à {parts['location']}" if fr else f"in {parts['location']}"
    )
    intro = (
        f"Nous souhaitons une soumission pour {parts['product']} pour notre "
        f"{parts['activity']} {place}."
        if fr
        else f"We would like a quote for {parts['product']} for our {parts['activity']} {place}."
    )
    greeting, closing = ("Bonjour,", "Cordialement,") if fr else ("Hello,", "Best regards,")
    subject = "Demande de soumission" if fr else "Quote request"
    signature = (
        "Envoyé de mon iPhone"
        if style == "noisy" and fr
        else ("Sent from my iPhone" if style == "noisy" else "The broker team")
    )
    return (
        f"Subject: {subject}\n\n{greeting}\n\n{intro}\n"
        + " ".join(body)
        + f"\n\n{closing}\n{signature}\n"
    )


def build_case(
    rng: random.Random,
    family: str,
    number: int,
    *,
    product: str = "commercial_property",
    activity: str | None = None,
    include: frozenset[str] = ALL_FIELDS,
    claims: tuple[tuple[int, str, int], ...] = (),
    claims_none: bool = False,
    style: str = "email",
    lang: str = "en",
    revenue: int | None = None,
    employees: int | None = None,
    year: int | None = None,
    coverage_phrase: str | None = None,
    coverage_override: tuple[str, ...] | None = None,
    money_format: str | None = None,
    postal_format: str = "standard",
    location_mode: str = "full",
    accented_city: bool = False,
    second_site: bool = False,
) -> tuple[dict[str, Any], str]:
    case_id = f"gen_{family}_{number:02d}"
    is_property = product in {"commercial_property", "business_package"}
    activity_key = activity or rng.choice(PROPERTY_ACTIVITIES if is_property else OTHER_ACTIVITIES)
    activity_en, activity_fr, accepted, _ = ACTIVITIES[activity_key]
    accepted_values = [*accepted, activity_fr] if lang == "fr" else accepted

    city, province, postal_first, province_name = rng.choice(CITIES)
    if accented_city:
        city, province, postal_first, province_name = rng.choice(ACCENTED_CITIES)
    postal = postal_code(rng, postal_first)
    postal_text = format_postal(postal, postal_format)
    has_province = "province" in include
    has_postal = "postal" in include
    city_value: str | None = city
    if location_mode == "postal_only":
        has_province, has_postal, city_value = False, True, None
    elif location_mode == "province_only":
        has_province, has_postal, city_value = True, False, None
    revenue_value = (
        revenue if revenue is not None else rng.choice([450_000, 780_000, 1_200_000, 2_500_000])
    )
    employees_value = employees if employees is not None else rng.randint(3, 60)
    year_value = year if year is not None else rng.randint(1965, 2010)
    name = rng.choice(NAMES[activity_key])
    coverages = DEFAULT_COVERAGES[product]
    if product == "commercial_property" and rng.random() < 0.4:
        coverages = coverages[:1]
    if coverage_override is not None:
        coverages = list(coverage_override)

    lang_index = 1 if lang == "fr" else 0
    location = city
    location_in: str | None = None
    if location_mode == "street":
        location = f"{rng.choice(STREETS[lang_index])}, {city}"
    if location_mode in {"full", "street"}:
        if has_province:
            province_text = province_name if rng.random() < 0.5 else province
            if lang == "fr" and province == "QC":
                province_text = "Québec"
            location += f", {province_text}"
        if has_postal:
            location += f" {postal_text}"
    elif location_mode == "postal_only":
        location = postal_text
        location_in = ("au code postal " if lang == "fr" else "at postal code ") + postal_text
    elif location_mode == "province_only":
        province_label = "Québec" if lang == "fr" and province == "QC" else province_name
        location = province_label
        location_in = (
            f"dans la province de {province_label}"
            if lang == "fr"
            else f"in the province of {province_label}"
        )
    second_site_text = second_site_form = None
    if second_site:
        city2, prov2, first2, _ = rng.choice([c for c in CITIES if c[0] != city])
        postal2 = postal_code(rng, first2)
        second_site_form = f"{city2}, {prov2} {postal2}"
        second_site_text = (
            f"Nous exploitons également un deuxième site à {city2}, {prov2} {postal2}."
            if lang == "fr"
            else f"We also operate a second location in {city2}, {prov2} {postal2}."
        )

    parts: dict[str, Any] = {
        "product": PRODUCTS[product][lang_index],
        "activity": activity_fr if lang == "fr" else activity_en,
        "location": location,
        "location_in": location_in,
        "second_site": second_site_text,
        "second_site_form": second_site_form,
        "name": name if "name" in include else None,
        "year": year_value if "year" in include else None,
        "employees": employees_value if "employees" in include else None,
        "employees_n": employees_value,
        "revenue": (
            money(rng, revenue_value, lang, money_format) if "revenue" in include else None
        ),
        "revenue_n": revenue_value,
        "coverages": (
            [COVERAGE_TEXT[c][lang_index] for c in coverages] if "coverages" in include else []
        ),
        "claims": [
            {
                "year": claim_year,
                "kind": CLAIM_TEXT[kind][lang_index],
                "amount": money(rng, amount, lang),
            }
            for claim_year, kind, amount in claims
        ],
        "claims_none": claims_none,
        "coverage_sentence": coverage_phrase,
    }
    text = render_text(rng, style, lang, parts)

    oracle = InsuranceSubmission(
        submission_id=case_id,
        product_line=ProductLine(product),
        business_activity=accepted[0],
        location_city=city_value,
        location_province=province if has_province else None,
        postal_code=postal if has_postal else None,
        building_construction_year=year_value if "year" in include else None,
        employee_count=employees_value if "employees" in include else None,
        annual_revenue_cad=float(revenue_value) if "revenue" in include else None,
        requested_coverages=(
            [CoverageType(c) for c in coverages] if "coverages" in include else []
        ),
        claims_history=[
            ClaimRecord(year=y, claim_type=ClaimType(k), amount_cad=float(a)) for y, k, a in claims
        ],
        claims_history_status=(
            ClaimsHistoryStatus.LOSSES_REPORTED
            if claims
            else ClaimsHistoryStatus.NO_LOSSES_REPORTED
            if claims_none
            else ClaimsHistoryStatus.NOT_PROVIDED
        ),
    )
    report = validate_submission(normalize_submission(oracle))

    expected_fields: dict[str, Any] = {
        "product_line": product,
        **({"location_city": city} if city_value is not None and not accented_city else {}),
        "requested_coverages": [c for c in coverages] if "coverages" in include else [],
        "claims_history_status": oracle.claims_history_status.value,
    }
    optional = {
        "insured_name": name if "name" in include else None,
        "location_province": oracle.location_province,
        "postal_code": oracle.postal_code,
        "building_construction_year": oracle.building_construction_year,
        "employee_count": oracle.employee_count,
        "annual_revenue_cad": oracle.annual_revenue_cad,
    }
    expected_fields.update({k: v for k, v in optional.items() if v is not None})
    if lang == "fr":
        expected_fields["source_language"] = "fr"

    case: dict[str, Any] = {
        "case_id": case_id,
        "input_file": f"{INPUT_PREFIX}/{case_id}.txt",
        "expected_fields": expected_fields,
        "acceptable_field_values": {
            "business_activity": accepted_values,
            **({"location_city": [city, fold_accents(city)]} if accented_city else {}),
        },
        "expected_missing_fields": report.missing_fields,
        "expected_flag_codes": [flag.code for flag in report.data_quality_flags],
        "expected_review_required": report.review_required,
    }
    if claims:
        case["expected_claim_years"] = sorted(y for y, _, _ in claims)
    elif claims_none:
        case["expected_claim_years"] = []
    return case, text


def specifications() -> list[tuple[str, dict[str, Any]]]:
    """Return (family, build_case kwargs) pairs covering the scenario matrix."""
    specs: list[tuple[str, dict[str, Any]]] = []
    styles = ["email", "form", "email", "noisy"]
    no_geo = ALL_FIELDS - {"province", "postal"}

    for i in range(10):
        specs.append(("complete", {"style": styles[i % 4], "claims_none": i % 2 == 0}))
    for i in range(4):
        product = [
            "commercial_property",
            "cyber",
            "commercial_general_liability",
            "business_package",
        ]
        specs.append(
            (
                "french",
                {
                    "lang": "fr",
                    "product": product[i],
                    "activity": "restaurant" if i in (0, 3) else None,
                    "style": "form" if i == 3 else "email",
                    "claims_none": True,
                },
            )
        )
    for i in range(4):
        specs.append(("no_geo", {"include": no_geo, "style": styles[i % 4], "claims_none": True}))
    for _ in range(4):
        specs.append(("no_postal", {"include": ALL_FIELDS - {"postal"}, "claims_none": True}))
    for i in range(4):
        specs.append(
            (
                "no_year",
                {"include": ALL_FIELDS - {"year"}, "style": styles[i % 4], "claims_none": True},
            )
        )
    for _ in range(3):
        specs.append(("no_revenue", {"include": ALL_FIELDS - {"revenue"}, "claims_none": True}))
    for i in range(4):
        specs.append(
            (
                "no_coverage",
                {
                    "include": ALL_FIELDS - {"coverages"},
                    "product": [
                        "commercial_property",
                        "cyber",
                        "business_package",
                        "commercial_general_liability",
                    ][i],
                    "claims_none": True,
                },
            )
        )
    kinds = ["fire", "water_damage", "theft"]
    for i in range(6):
        claim_years = [(2012 + i, kinds[i % 3], 12_000 + 5_500 * i)]
        if i % 2:
            claim_years.append((2009 - i, kinds[(i + 1) % 3], 8_000))
        specs.append(("claims_reported", {"claims": tuple(claim_years), "style": styles[i % 4]}))
    for i in range(5):
        specs.append(("claims_none", {"claims_none": True, "style": styles[i % 4]}))
    for i in range(4):
        specs.append(
            (
                "claim_before_build",
                {
                    "year": 2021 + i % 3,
                    "claims": ((2016 + i, kinds[i % 3], 15_000),),
                    "style": styles[i % 4],
                },
            )
        )
    for i, product in enumerate(["cyber"] * 3 + ["commercial_general_liability"] * 3):
        specs.append(
            (
                "non_property",
                {"product": product, "claims_none": i % 2 == 0, "style": styles[i % 4]},
            )
        )
    for _ in range(2):
        specs.append(("zero_revenue", {"revenue": 0, "claims_none": True}))
    for _ in range(2):
        specs.append(("zero_employees", {"employees": 0, "claims_none": True}))
    for i in range(5):
        specs.append(
            (
                "noisy_distractors",
                {"style": "noisy", "include": ALL_FIELDS - {"year"}, "claims_none": i % 2 == 0},
            )
        )
    for phrase, covs, lang in COVERAGE_PHRASINGS:
        specs.append(
            (
                "coverage_phrasing",
                {
                    "coverage_phrase": phrase,
                    "coverage_override": covs,
                    "lang": lang,
                    "activity": "restaurant",
                    "claims_none": True,
                },
            )
        )
    specs.extend(edge_case_specifications())
    return specs


def edge_case_specifications() -> list[tuple[str, dict[str, Any]]]:
    """Edge-case families, appended after the original matrix so earlier cases are unchanged."""
    specs: list[tuple[str, dict[str, Any]]] = []
    formats = [
        ("fr", 1_200_000, "fr_m", "lower_compact", "restaurant", "email"),
        ("fr", 2_500_000, "fr_millions", "dashed", "retail", "email"),
        ("fr", 780_000, "fr_decimal", "no_space", "warehouse", "noisy"),
        ("fr", 450_000, "fr_k", "standard", "restaurant", "form"),
        ("en", 450_000, "en_k", "lower_compact", "retail", "email"),
        ("en", 1_200_000, "en_million", "dashed", "restaurant", "form"),
        ("en", 2_500_000, "en_million", "no_space", "warehouse", "noisy"),
    ]
    for lang, revenue, money_format, postal_format, activity, style in formats:
        specs.append(
            (
                "number_formats",
                {
                    "lang": lang,
                    "revenue": revenue,
                    "money_format": money_format,
                    "postal_format": postal_format,
                    "activity": activity,
                    "style": style,
                    "claims_none": True,
                },
            )
        )
    for mode in ("postal_only", "province_only", "street"):
        for lang in ("en", "fr"):
            specs.append(
                (
                    "partial_address",
                    {
                        "lang": lang,
                        "location_mode": mode,
                        "activity": "restaurant",
                        "claims_none": True,
                    },
                )
            )
    for lang, style in [("fr", "email"), ("fr", "form"), ("en", "email")]:
        specs.append(
            (
                "accented_city",
                {"lang": lang, "style": style, "accented_city": True, "claims_none": True},
            )
        )
    for activity, lang, style in [
        ("convenience_restaurant", "en", "email"),
        ("convenience_restaurant", "fr", "email"),
        ("bakery_cafe", "en", "noisy"),
        ("bakery_cafe", "fr", "form"),
    ]:
        specs.append(
            (
                "ambiguous_activity",
                {"activity": activity, "lang": lang, "style": style, "claims_none": True},
            )
        )
    for lang, style in [("en", "email"), ("fr", "email"), ("en", "noisy"), ("en", "form")]:
        specs.append(
            (
                "multi_site",
                {"lang": lang, "style": style, "second_site": True, "claims_none": True},
            )
        )
    return specs


def generate(
    output_directory: Path, dataset_path: Path, base_dataset: Path
) -> list[dict[str, Any]]:
    rng = random.Random(SEED)
    counters: dict[str, int] = {}
    cases: list[dict[str, Any]] = []

    output_directory.mkdir(parents=True, exist_ok=True)
    for stale in output_directory.glob("gen_*.txt"):
        stale.unlink()

    for family, kwargs in specifications():
        counters[family] = counters.get(family, 0) + 1
        case, text = build_case(rng, family, counters[family], **kwargs)
        (output_directory / f"{case['case_id']}.txt").write_text(text, encoding="utf-8")
        cases.append(case)

    base_lines = [
        line for line in base_dataset.read_text(encoding="utf-8").splitlines() if line.strip()
    ]
    generated_lines = [json.dumps(c, ensure_ascii=False, separators=(",", ":")) for c in cases]
    dataset_path.parent.mkdir(parents=True, exist_ok=True)
    dataset_path.write_text("\n".join(base_lines + generated_lines) + "\n", encoding="utf-8")
    return cases


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output-directory", type=Path, default=OUTPUT_DIRECTORY)
    parser.add_argument("--dataset", type=Path, default=OUTPUT_DATASET)
    parser.add_argument("--base-dataset", type=Path, default=BASE_DATASET)
    args = parser.parse_args()

    cases = generate(args.output_directory, args.dataset, args.base_dataset)
    print(f"Generated {len(cases)} cases -> {args.dataset}")


if __name__ == "__main__":
    main()
