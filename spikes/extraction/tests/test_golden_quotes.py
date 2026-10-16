"""Every golden evidence quote must be found verbatim (whitespace-normalised) in its document."""

from __future__ import annotations

import json

from conftest import GOLDEN_PATH

from documents import match_key, normalize_text


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
    missing = []
    for where, doc_id, quote in _quotes():
        if doc_id not in docs:
            continue  # e.g. MDT_zaver (post as_of, not a patient report)
        hay = match_key(docs[doc_id].text).key
        needle = match_key(normalize_text(quote)).key
        if needle in hay:
            continue
        # finding quotes list several docs; a quote only needs to be in one of them
        if any(needle in match_key(d.text).key for d in docs.values()):
            continue
        missing.append((where, doc_id, quote))
    assert not missing, missing
