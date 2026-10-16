"""Shared fixtures for document/extraction tests: the 13 fictitious reports, normalised (owner: P2).

Imported by the conftest of tests/unit/documents, tests/unit/extraction and tests/eval.
"""

from __future__ import annotations

from collections.abc import Callable

import pytest

from app.documents.normalize import NormalizedDoc, normalize
from app.settings import REPO_ROOT

DOCS_DIR = REPO_ROOT / "data" / "raw" / "Pacient"
GOLDEN_PATH = REPO_ROOT / "data" / "golden" / "expected_handover_2026-10-21.json"


@pytest.fixture(scope="session")
def docs() -> dict[str, NormalizedDoc]:
    return {p.stem: normalize(p) for p in sorted(DOCS_DIR.glob("*.docx"))}


@pytest.fixture(scope="session")
def doc(docs: dict[str, NormalizedDoc]) -> Callable[[str], NormalizedDoc]:
    def get(prefix: str) -> NormalizedDoc:
        (match,) = [d for k, d in docs.items() if k.startswith(prefix)]
        return match

    return get
