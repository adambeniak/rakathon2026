"""Business ids of new cases: 'rakathon-<year>-<ascii family name>-<6 hex>' (no RČ in ids, data minimisation).

The random suffix makes the id collision-resistant without a reservation step: two simultaneous referrals of different
patients with the same family name cannot end up with one id (24 bits per family and year; the writer still checks).
"""

from __future__ import annotations

import re
import secrets
import unicodedata
from collections.abc import Iterator

PREFIX = "rakathon"


def slug(family: str) -> str:
    folded = unicodedata.normalize("NFKD", family).encode("ascii", "ignore").decode("ascii").lower()
    return re.sub(r"[^a-z0-9]+", "-", folded).strip("-")[:40] or "pacient"


def case_id_candidates(year: int, family: str) -> Iterator[str]:
    """'rakathon-2026-prochazkova-3fa9c1', then further random suffixes."""
    base = f"{PREFIX}-{year}-{slug(family)}"
    while True:
        yield f"{base}-{secrets.token_hex(3)}"
