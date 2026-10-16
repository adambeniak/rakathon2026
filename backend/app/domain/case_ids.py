"""Business ids of new cases: 'rakathon-<year>-<ascii family name>' (no RČ in ids, data minimisation)."""

from __future__ import annotations

import re
import unicodedata
from collections.abc import Iterator
from itertools import count

PREFIX = "rakathon"


def slug(family: str) -> str:
    folded = unicodedata.normalize("NFKD", family).encode("ascii", "ignore").decode("ascii").lower()
    return re.sub(r"[^a-z0-9]+", "-", folded).strip("-")[:40] or "pacient"


def case_id_candidates(year: int, family: str) -> Iterator[str]:
    """'rakathon-2026-prochazkova', then '…-2', '…-3'."""
    base = f"{PREFIX}-{year}-{slug(family)}"
    yield base
    for number in count(2):
        yield f"{base}-{number}"
