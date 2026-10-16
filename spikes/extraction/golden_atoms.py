"""Atomic expected values derived from the golden handover (the golden file is never edited).

Matching rules were fixed before the first eval run:
- numbers compare numerically (comma/point agnostic), codes and identifiers exactly after fold,
- dates compare as ISO,
- medications = drug + dose + schedule,
- labs = test name + value + unit + document (+ date: clinical_date equal or null),
- free text (comorbidity / symptom / other items) is NOT a key value; it is reported separately as
  text coverage (share of golden content stems found in the best single fact).
"""

from __future__ import annotations

import re
import unicodedata
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from decimal import Decimal
from typing import Any

from extraction import fold, numbers_in
from schema import CodedValue, DateValue, Fact, MedicationValue, PersonValue, QuantityValue

Matcher = Callable[[Sequence[Fact]], bool]


@dataclass(frozen=True)
class Atom:
    atom_id: str
    field: str
    description: str
    match: Matcher
    negative: bool = False  # True = must NOT be found (a hit is a hallucination)


# ---------------------------------------------------------------- fact text helpers


def value_strings(f: Fact) -> list[str]:
    out: list[str] = []
    for k, v in f.value.model_dump().items():
        if k != "kind" and isinstance(v, str):
            out.append(v)
    if f.unit:
        out.append(f.unit)
    return out


def value_text(f: Fact) -> str:
    return fold(" ".join(value_strings(f)))


def _num(x: float | int | str) -> Decimal:
    return Decimal(str(x).replace(",", ".")).normalize()


def _has(f: Fact, needle: str, *, in_quote: bool = False) -> bool:
    hay = value_text(f) + (" " + fold(f.quote) if in_quote else "")
    return fold(needle) in hay


def _dates(f: Fact) -> set[str]:
    out = {f.clinical_date} if f.clinical_date else set()
    if isinstance(f.value, DateValue):
        out.add(f.value.date)
    return out


def _of(facts: Sequence[Fact], types: set[str], fields: set[int] | None = None) -> list[Fact]:
    return [f for f in facts if f.type in types or (fields is not None and f.handover_field in fields)]


# ---------------------------------------------------------------- text coverage (secondary metric)

_STOP = {
    "a", "i", "v", "ve", "s", "se", "z", "ze", "na", "do", "po", "pro", "od", "k", "ke", "o", "u",
    "the", "je", "jsou", "při", "za", "než", "nebo", "t", "c",
}  # fmt: skip


def stems(text: str) -> set[str]:
    base = unicodedata.normalize("NFKD", fold(text))
    base = "".join(ch for ch in base if not unicodedata.combining(ch))
    return {w[:5] for w in re.findall(r"\w+", base) if w not in _STOP}


def text_coverage(expected: str, facts: Sequence[Fact]) -> float:
    want = stems(expected)
    if not want:
        return 1.0
    best = 0.0
    for f in facts:
        have = stems(" ".join(value_strings(f)) + " " + f.quote)
        best = max(best, len(want & have) / len(want))
    return best


# ---------------------------------------------------------------- atoms


def _sign_word(sign: str) -> str:
    return {"+": "pozitiv", "-": "negativ"}.get(sign, sign)


def _any_has(needle: str, types: set[str], fields: set[int] | None = None) -> Matcher:
    return lambda fs: any(_has(f, needle) for f in _of(fs, types, fields))


def _any_date(iso: str, types: set[str], fields: set[int] | None = None, doc_prefix: str = "") -> Matcher:
    return lambda fs: any(iso in _dates(f) for f in _of(fs, types, fields) if f.doc_id.startswith(doc_prefix))


def _insurer(code: str) -> Matcher:
    return lambda fs: any(
        (isinstance(f.value, CodedValue) and f.value.code == code) or re.search(rf"\b{code}\b", value_text(f))
        for f in _of(fs, {"insurer"}, {1})
    )


def _ihc(marker: str, word: str) -> Matcher:
    pat = rf"(?<!\w){re.escape(fold(marker))}(?!\w)"
    histo = {"histology", "diagnosis", "admin_date", "examination"}
    return lambda fs: any(re.search(pat, value_text(f)) and fold(word) in value_text(f) for f in _of(fs, histo, {14}))


def build_atoms(golden: dict[str, Any]) -> list[Atom]:
    g = golden["fields"]
    atoms: list[Atom] = []

    def add(atom_id: str, field: str, desc: str, match: Matcher, negative: bool = False) -> None:
        atoms.append(Atom(atom_id, field, desc, match, negative))

    # 1 patient (derived: sex, age_years, insurer_name, checksum -> excluded)
    p = g["1_patient"]["value"]
    ident = {"patient_identity", "insurer", "contact"}
    for key in ("given", "family", "birth_number", "address"):
        val = p[key]
        add(f"1.{key}", "1_patient", val, _any_has(val, ident, {1, 2}))
    add("1.birth_date", "1_patient", p["birth_date"], _any_date(p["birth_date"], {"patient_identity"}, {1}))
    add("1.insurer_code", "1_patient", p["insurer_code"], _insurer(p["insurer_code"]))

    # 2 contacts
    c = g["2_contacts"]["value"]
    cp = c["contact_person"]
    for aid, val in (
        ("2.patient_phone", c["patient_phone"]),
        ("2.contact_name", cp["name"]),
        ("2.contact_relation", cp["relation"]),
        ("2.contact_phone", cp["phone"]),
    ):
        add(aid, "2_contacts", val, _any_has(val, {"contact"}, {2}))
    add(
        "2.no_patient_email",
        "2_contacts",
        "no e-mail is documented",
        lambda fs: any(isinstance(f.value, PersonValue) and f.value.email for f in fs)
        or any("@" in f.quote for f in fs),
        negative=True,
    )

    # 3 diagnosis
    d = g["3_diagnosis"]["value"]
    dx = {"diagnosis", "histology", "referral_request"}
    add("3.icd10", "3_diagnosis", d["icd10"], _any_has(d["icd10"], dx, {3}))
    add("3.icdo3", "3_diagnosis", d["icdo3_morphology"], _any_has(d["icdo3_morphology"], dx, {3, 14}))
    histo_date = d["verified_histologically_on"]
    add("3.histology_date", "3_diagnosis", histo_date, _any_date(histo_date, dx | {"admin_date"}, None, "11_"))
    add(
        "3.no_tnm",
        "3_diagnosis",
        "no TNM stage is documented",
        lambda fs: any(re.search(r"\bc?T[0-4x][a-d]?\s*N[0-3x]", " ".join(value_strings(f))) for f in fs)
        or any("TNM" in " ".join(value_strings(f)) for f in fs),
        negative=True,
    )

    # 6 comorbidities: codes + EF are key values; texts -> coverage
    for item in g["6_comorbidities"]["value"]:
        if "icd10" in item:
            code = item["icd10"]
            add(f"6.{code}", "6_comorbidities", code, _any_has(code, {"comorbidity", "diagnosis"}, {6}))
    add(
        "6.ef_lk",
        "6_comorbidities",
        "EF LK 60 %",
        lambda fs: any(
            isinstance(f.value, QuantityValue)
            and "ef" in fold(f.value.name)
            and f.value.number is not None
            and _num(f.value.number) == _num(60)
            for f in fs
        ),
    )

    # 7 medications
    for med in g["7_medications"]["value"]:
        drug, dose, sched = med["drug"], med["dose"], med["schedule"]

        def med_match(fs: Sequence[Fact], drug: str = drug, dose: str = dose, sched: str = sched) -> bool:
            for f in fs:
                v = f.value
                if not isinstance(v, MedicationValue) or fold(drug) not in fold(v.drug):
                    continue
                if not v.dose or numbers_in(v.dose) != numbers_in(dose) or fold("mg") not in fold(v.dose):
                    continue
                if not v.schedule:
                    continue
                if re.fullmatch(r"[\d\s\-–]+", sched):  # dosing notation 1-0-1: exact
                    if re.sub(r"\s", "", sched) == re.sub(r"\s", "", v.schedule):
                        return True
                elif fold(sched) in fold(v.schedule) or stems(sched) <= stems(v.schedule):
                    return True
            return False

        add(f"7.{drug}", "7_medications", f"{drug} {dose} {sched}", med_match)

    # 8 allergies
    add(
        "8.neguje",
        "8_allergies",
        "AA: neguje",
        lambda fs: any(f.type == "allergy" and (f.certainty == "negated" or "neguje" in value_text(f)) for f in fs),
    )

    # 9 performance status: expected missing -> any PS fact is a hallucination
    add(
        "9.no_ps",
        "9_performance_status",
        "no ECOG/Karnofsky fact",
        lambda fs: any(f.type == "performance_status" for f in fs),
        negative=True,
    )

    # 10 weight / height
    wh = g["10_weight_height"]["value"]
    vitals: list[tuple[str, Any, str, str]] = [("height", wh["height_cm"], "cm", wh["height_date"])]
    vitals += [("weight", w["kg"], "kg", w["date"]) for w in wh["weights"]]
    for kind, number, unit, when in vitals:

        def vital_match(fs: Sequence[Fact], number: Any = number, unit: str = unit, when: str = when) -> bool:
            return any(
                isinstance(f.value, QuantityValue)
                and f.value.number is not None
                and _num(f.value.number) == _num(number)
                and (fold(unit) == fold(f.unit or "") or fold(unit) in fold(f.quote))
                and (when in _dates(f) or f.doc_id.endswith(when))
                for f in _of(fs, {"vital_sign", "examination"}, {10})
            )

        add(f"10.{kind}.{when}", "10_weight_height", f"{kind} {number} {unit} ({when})", vital_match)

    # 11 symptom onset (date); items -> coverage
    add(
        "11.onset",
        "11_symptoms",
        g["11_symptoms"]["value"]["onset"],
        lambda fs: any(
            f.type == "symptom" and ("2026-08" in {x[:7] for x in _dates(f)} or "poloviny srpna 2026" in fold(f.quote))
            for f in fs
        ),
    )

    # 12 examinations: a dated clinical fact from each document
    for ex in g["12_examinations"]["value"]:
        doc, when = ex["doc"], ex["date"]
        clinical = {"examination", "procedure", "lab_result", "histology"}  # header-date lines do not count
        add(f"12.{doc[:2]}", "12_examinations", f"{ex['type']} {when}", _any_date(when, clinical, None, doc))

    # 13 labs
    for lab in g["13_labs"]["key_values"]:

        def lab_match(fs: Sequence[Fact], lab: dict[str, Any] = lab) -> bool:
            for f in fs:
                v = f.value
                if f.doc_id != lab["doc"] or not isinstance(v, QuantityValue) or v.number is None:
                    continue
                if fold(v.name) != fold(lab["test"]) and not fold(v.name).startswith(fold(lab["test"])):
                    continue
                if _num(v.number) != _num(lab["value"]) or fold(f.unit or "") != fold(lab["unit"]):
                    continue
                if lab.get("flag") != v.flag:
                    continue
                if f.clinical_date not in (None, lab["date"]):
                    continue
                return True
            return False

        add(
            f"13.{lab['test']}.{lab['date']}",
            "13_labs",
            f"{lab['test']} {lab['value']} {lab['unit']} {lab.get('flag', '')} ({lab['date']})",
            lab_match,
        )

    # 14 histology
    h = g["14_histology"]["value"]
    histo = {"histology", "diagnosis", "admin_date", "examination"}
    add("14.report_id", "14_histology", h["report_id"], _any_has(h["report_id"], histo, {14}))
    for marker, result in h["ihc"].items():
        add(f"14.ihc.{marker}", "14_histology", f"{marker} {result}", _ihc(marker, _sign_word(result)))
    add(
        "14.perineural",
        "14_histology",
        "perineurální invaze",
        lambda fs: any("perineurální invaz" in value_text(f) for f in _of(fs, histo, {14, 3})),
    )
    add("14.grade", "14_histology", h["grade"], _any_has(h["grade"], histo, {14, 3}))
    return atoms


def coverage_items(golden: dict[str, Any]) -> list[tuple[str, str, set[str]]]:
    """(field, expected text, candidate types) for the secondary free-text coverage metric."""
    g = golden["fields"]
    out: list[tuple[str, str, set[str]]] = []
    for item in g["6_comorbidities"]["value"]:
        out.append(("6_comorbidities", item["text"], {"comorbidity", "diagnosis"}))
    for s in g["11_symptoms"]["value"]["items"]:
        out.append(("11_symptoms", s, {"symptom"}))
    for s in g["15_other"]["value"]:
        out.append(("15_other", s, {"consent_or_wish", "documented_plan", "referral_request", "symptom"}))
    return out
