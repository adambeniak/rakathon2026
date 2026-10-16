from __future__ import annotations

import sys
from pathlib import Path

import pytest

SPIKE = Path(__file__).resolve().parents[1]
REPO = SPIKE.parents[1]
sys.path.insert(0, str(SPIKE))

from documents import NormalizedDoc, normalize  # noqa: E402

DOCS_DIR = REPO / "data" / "raw" / "Pacient"
GOLDEN_PATH = REPO / "data" / "golden" / "expected_handover_2026-10-21.json"


@pytest.fixture(scope="session")
def docs() -> dict[str, NormalizedDoc]:
    return {p.stem: normalize(p) for p in sorted(DOCS_DIR.glob("*.docx"))}


@pytest.fixture(scope="session")
def doc(docs: dict[str, NormalizedDoc]):  # type: ignore[no-untyped-def]
    def get(prefix: str) -> NormalizedDoc:
        (match,) = [d for k, d in docs.items() if k.startswith(prefix)]
        return match

    return get
