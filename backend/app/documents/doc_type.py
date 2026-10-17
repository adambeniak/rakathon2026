"""LOINC document type of an uploaded report, inferred from its file name (owner: P2).

The seeded documents carry their type by hand; an uploaded one has only its name. The handover rules read the type
(a drug in a procedure note is not medication history, lab values come from lab reports, ...), so an untyped upload
silently changes them. Only the words of the name are used, never the content. A name that matches no rule stays
untyped (None) and the rules treat it as before.
"""

from __future__ import annotations

import re
import unicodedata
from typing import Final

CONSULT_NOTE: Final = "11488-4"
LAB_REPORT: Final = "11502-2"
IMAGING: Final = "18748-4"
REFERRAL_NOTE: Final = "57133-1"
PROCEDURE_NOTE: Final = "28570-0"
PATHOLOGY: Final = "11526-1"

# First match wins, so the specific kinds (pathology, procedure) come before the broad ones. A word matches by prefix
# ("histolog" -> Histologie); short abbreviations must match the whole word.
_RULES: Final[tuple[tuple[str, tuple[str, ...], tuple[str, ...]], ...]] = (
    (PATHOLOGY, ("histolog", "patolog", "cytolog"), ()),
    (PROCEDURE_NOTE, ("biops", "vykon", "operac", "endoskop"), ()),
    (LAB_REPORT, ("laborator", "biochem"), ("lab",)),
    (IMAGING, ("rentgen", "sonograf", "tomograf", "rezonanc", "zobraz"), ("rtg", "uz", "ct", "mr", "pet")),
    (REFERRAL_NOTE, ("zadost", "epikriz"), ()),
    (CONSULT_NOTE, ("kardiolog", "gastro", "algezi", "psycho", "ambulant", "konzil", "onkolog"), ()),
)


def _words(name: str) -> list[str]:
    plain = "".join(c for c in unicodedata.normalize("NFKD", name.lower()) if not unicodedata.combining(c))
    return [w for w in re.split(r"[^a-z]+", plain) if w]


def infer_type_code(name: str) -> str | None:
    """LOINC type for a file stem or name such as '09_Biopsie_vykon_KOC2_2026-10-12', or None when unknown."""
    words = _words(name)
    for code, prefixes, exact in _RULES:
        if any(w in exact or w.startswith(prefixes) for w in words):
            return code
    return None
