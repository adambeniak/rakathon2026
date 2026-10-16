"""Matchers of the golden atoms (fixed before the first eval run)."""

from __future__ import annotations

import json
from typing import Any

from conftest import GOLDEN_PATH

from extraction import Accepted, evidence_lock
from golden_atoms import build_atoms, stems, text_coverage
from schema import Fact, RawFact


def _golden() -> dict[str, Any]:
    return json.loads(GOLDEN_PATH.read_text(encoding="utf-8"))


def _atom(atom_id: str):  # type: ignore[no-untyped-def]
    (a,) = [a for a in build_atoms(_golden()) if a.atom_id == atom_id]
    return a


def _fact(doc, **kw: Any) -> Fact:  # type: ignore[no-untyped-def]
    base: dict[str, Any] = {"unit": None, "clinical_date": None, "certainty": "stated"}
    base.update(kw)
    r = evidence_lock(RawFact.model_validate(base), doc)
    assert isinstance(r, Accepted), r
    return r.fact


def _q(name: str, number: float, flag: str | None = None) -> dict[str, Any]:
    return {"kind": "quantity", "name": name, "number": number, "text_value": None,
            "comparator": None, "flag": flag, "ref_range": None}  # fmt: skip


def test_atoms_built() -> None:
    atoms = build_atoms(_golden())
    ids = {a.atom_id for a in atoms}
    assert {"13.CA 19-9.2026-10-15", "7.apixaban", "9.no_ps", "1.birth_number"} <= ids
    assert len([a for a in atoms if not a.negative]) >= 50


def test_lab_numeric_match_across_comma(doc) -> None:  # type: ignore[no-untyped-def]
    f = _fact(
        doc("10_"),
        type="lab_result",
        handover_field=13,
        value=_q("CEA", 4.1),
        unit="µg/l",
        quote="CEA | 4,1 | µg/l | < 5,0",
        clinical_date="2026-10-15",
    )
    assert _atom("13.CEA.2026-10-15").match([f])


def test_lab_flag_must_match(doc) -> None:  # type: ignore[no-untyped-def]
    f = _fact(
        doc("10_"),
        type="lab_result",
        handover_field=13,
        value=_q("CA 19-9", 312),  # flag missing
        unit="kU/l",
        quote="CA 19-9 | 312 H | kU/l | < 37",
    )
    assert not _atom("13.CA 19-9.2026-10-15").match([f])


def test_med_triple(doc) -> None:  # type: ignore[no-untyped-def]
    q = "FA: apixaban 5 mg 1-0-1, bisoprolol 5 mg 1-0-0"
    good = _fact(
        doc("07_"),
        type="medication",
        handover_field=7,
        value={"kind": "medication", "drug": "apixaban", "dose": "5 mg", "schedule": "1-0-1"},
        quote=q,
    )
    wrong_sched = _fact(
        doc("07_"),
        type="medication",
        handover_field=7,
        value={"kind": "medication", "drug": "apixaban", "dose": "5 mg", "schedule": "1-0-0"},
        quote=q,
    )
    assert _atom("7.apixaban").match([good])
    assert not _atom("7.apixaban").match([wrong_sched])


def test_negative_ps_atom(doc) -> None:  # type: ignore[no-untyped-def]
    assert not _atom("9.no_ps").match([])


def test_stems_and_coverage(doc) -> None:  # type: ignore[no-untyped-def]
    assert "prech" in stems("přechodně")
    f = _fact(
        doc("07_"),
        type="comorbidity",
        handover_field=6,
        value={"kind": "text", "text": "v r. 2019 po úmrtí manžela přechodně depresivní ladění, neléčena"},
        quote="v r. 2019 po úmrtí manžela přechodně depresivní ladění, neléčena",
    )
    assert text_coverage("2019 přechodně depresivní ladění po úmrtí manžela, neléčena", [f]) == 1.0
