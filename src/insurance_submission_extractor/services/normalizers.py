from __future__ import annotations

import string
import unicodedata

from insurance_submission_extractor.schemas import InsuranceSubmission


def _key(text: str) -> str:
    """Compare activity names regardless of case, accents and Unicode composition."""
    decomposed = unicodedata.normalize("NFKD", text)
    stripped = "".join(char for char in decomposed if not unicodedata.combining(char))

    return " ".join(stripped.casefold().split())


_OCCUPANCY_PAIRS = (
    ("restaurant", "restaurant"),
    ("retail store", "retail store"),
    ("small retail store", "retail store"),
    ("warehouse", "warehouse"),
    ("entrepôt", "warehouse"),
    ("magasin de détail", "retail store"),
    ("commerce de détail", "retail store"),
)

OCCUPANCY_BY_BUSINESS_ACTIVITY = {
    _key(activity): occupancy for activity, occupancy in _OCCUPANCY_PAIRS
}


def normalize_postal_code(value: str) -> str:
    """Return a Canadian postal code as 'A1A 1A1'; leave any other value unchanged."""
    candidate = unicodedata.normalize("NFKC", value).upper()
    compact = "".join(char for char in candidate if char.isalnum())

    if len(compact) != 6:
        return value

    letters_ok = all(compact[index] in string.ascii_uppercase for index in (0, 2, 4))
    digits_ok = all(compact[index] in string.digits for index in (1, 3, 5))

    return f"{compact[:3]} {compact[3:]}" if letters_ok and digits_ok else value


def normalize_submission(
    submission: InsuranceSubmission,
) -> InsuranceSubmission:
    updates: dict[str, str] = {}

    if submission.postal_code is not None:
        postal_code = normalize_postal_code(submission.postal_code)
        if postal_code != submission.postal_code:
            updates["postal_code"] = postal_code

    if submission.occupancy_type is None and submission.business_activity is not None:
        occupancy_type = OCCUPANCY_BY_BUSINESS_ACTIVITY.get(_key(submission.business_activity))
        if occupancy_type is not None:
            updates["occupancy_type"] = occupancy_type

    return submission.model_copy(update=updates) if updates else submission
