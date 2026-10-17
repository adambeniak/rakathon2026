"""Document type (LOINC) of an uploaded report, inferred from its file name (#129)."""

from __future__ import annotations

import pytest

from app.documents.doc_type import infer_type_code
from app.seed.demo_case import DOCUMENTS


@pytest.mark.parametrize("doc", DOCUMENTS, ids=lambda d: d.doc_id)
def test_infers_the_type_the_seed_assigns_to_the_same_file(doc) -> None:  # type: ignore[no-untyped-def]
    assert infer_type_code(doc.doc_id) == doc.loinc


@pytest.mark.parametrize("name", ["scan001", "poznamky", "2026-10-12", ""])
def test_unknown_names_stay_untyped(name: str) -> None:
    assert infer_type_code(name) is None
