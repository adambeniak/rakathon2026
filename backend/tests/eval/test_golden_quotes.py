"""Every golden evidence quote must be found verbatim (whitespace-normalised) in its document."""

from __future__ import annotations

import json

from app.documents.normalize import match_key, normalize_text
from tests.document_fixtures import GOLDEN_PATH


def _quotes() -> list[tuple[str, str, str]]:
    g = json.loads(GOLDEN_PATH.read_text(encoding="utf-8"))
    out: list[tuple[str, str, str]] = []
    for name, field in g["fields"].items():
        for ev in field.get("evidence", []):
            out.append((name, ev["doc"], ev["quote"]))
    for f in g["expected_findings"]:
        for d in f.get("docs", []):
            for q in f.get("quotes", []):
                out.append((f["id"], d, q))
    return out


def test_golden_quotes_found(docs) -> None:  # type: ignore[no-untyped-def]
    golden = json.loads(GOLDEN_PATH.read_text(encoding="utf-8"))
    finding_docs = {f["id"]: f.get("docs", []) for f in golden["expected_findings"]}
    missing = []
    for where, doc_id, quote in _quotes():
        if doc_id not in docs:
            continue  # e.g. MDT_zaver (post as_of, not a patient report)
        needle = match_key(normalize_text(quote)).key
        allowed_docs = finding_docs.get(where, [doc_id])
        if any(needle in match_key(docs[d].text).key for d in allowed_docs if d in docs):
            continue
        missing.append((where, doc_id, quote))
    assert not missing, missing
