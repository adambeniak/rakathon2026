"""Handover eval vs the golden set (used by `make eval` via test_handover_eval.py).

Runs the cached extraction, the epicrisis (cached LLM, else the cited fallback) and `assemble_handover` for the
demo case, then compares field statuses and key values with data/golden. Findings come from the deterministic
consistency rules over the as-of-filtered facts (`detect_findings`); the eval never consumes golden-derived findings.
Results are merged into eval/report.json under "handover".
"""

from __future__ import annotations

import json
import re
from collections.abc import Iterator
from datetime import datetime
from decimal import Decimal
from typing import Any

from app.consistency import detect_findings
from app.documents.normalize import NormalizedDoc, normalize
from app.domain.document import SourceDocument
from app.domain.evidence import Fact
from app.domain.handover import Handover, HandoverFieldBase, HandoverFields, HandoverStatus
from app.extraction.handover.assemble import assemble_handover, included_facts, split_documents
from app.extraction.handover.epicrisis import check_sentences, generate_epicrisis, select_facts
from app.extraction.handover.facts import fold_text
from app.extraction.handover.fields import DOCUMENTED_PREFIX
from app.extraction.handover.headers import parse_headers
from app.extraction.lock import NEGATED_VALUE_REPAIRED, numbers_in
from app.extraction.pipeline import CompletionClient, extract_facts
from app.settings import PRAGUE
from tests.eval.extraction_eval import AS_OF, DOCS_DIR, GOLDEN, REPORT, load_docs, source_documents

from app.seed.demo_case import DOCUMENTS, ORGANIZATIONS, PATIENT  # isort: skip

CASE_ID = "rakathon-2026-prochazkova"
LATER_AS_OF = datetime(2026, 10, 28, 8, 0, tzinfo=PRAGUE)
# Fields 7 and 14 are complete_with_conflict in the golden set because of findings C1/C2 (app.consistency).
FIELD_STATUS_GATE = 14

# Values computed by a deterministic rule from a stated value, or document metadata: not expected in a quote.
DERIVED_KEYS = frozenset(
    {"sex", "age_years", "insurer_name", "birth_number_checksum_valid", "perineural_invasion", "ihc", "doc_id"}
)
_ISO_DATE = re.compile(r"^\d{4}-\d{2}-\d{2}$")
_ATTRIBUTION = re.compile(rf"^{DOCUMENTED_PREFIX} \(.*?, \d{{1,2}}\. \d{{1,2}}\. \d{{4}}\): ")


def item_problems(h: Handover) -> list[dict[str, Any]]:
    """Every field with a value shows it as items; every item has evidence (field 12 rows are document metadata)."""
    out: list[dict[str, Any]] = []
    for key, field in _fields(h):
        if getattr(field, "value", None) is not None and not field.items:
            out.append({"field": key, "why": "value without items"})
        if key == "12_examinations":
            continue
        out += [{"field": key, "why": f"item without evidence: {i.label}"} for i in field.items if not i.evidence]
    return out


def handover_documents() -> dict[str, SourceDocument]:
    """Seed metadata incl. the issuing workplace (custodian) shown in field 12."""
    names = {o.id: o.name for o in ORGANIZATIONS}
    custodians = {d.doc_id: names[d.custodian] for d in DOCUMENTS}
    return {k: d.model_copy(update={"custodian": custodians[k]}) for k, d in source_documents().items()}


async def extract_all(client: CompletionClient) -> tuple[dict[str, NormalizedDoc], list[Fact]]:
    docs = load_docs()
    facts = [f for d in docs.values() for f in (await extract_facts(d, client)).accepted]
    return docs, facts


async def build(
    facts: list[Fact],
    epicrisis_client: CompletionClient,
    as_of: datetime,
    docs: dict[str, NormalizedDoc] | None = None,
) -> tuple[Handover, list[Fact]]:
    documents = handover_documents()
    included, _ = split_documents(documents, as_of)
    known = included_facts(facts, included)
    field4 = await generate_epicrisis(known, included, epicrisis_client, case_id=CASE_ID)
    headers = parse_headers({k: v for k, v in docs.items() if k in included}) if docs is not None else None
    findings = detect_findings(known, headers, {k: d.type_code for k, d in included.items()})
    handover = assemble_handover(
        CASE_ID, as_of, known, documents, patient=PATIENT, findings=findings, epicrisis=field4, headers=headers
    )
    return handover, known


# ---------------------------------------------------------------- independent checks


def _fields(h: Handover) -> Iterator[tuple[str, HandoverFieldBase]]:
    for name, info in HandoverFields.model_fields.items():
        yield info.alias or name, getattr(h.fields, name)


def evidence_problems(h: Handover, fresh: dict[str, NormalizedDoc]) -> list[dict[str, Any]]:
    """Every evidence quote must be the exact span of a freshly normalised source (re-read from DOCX)."""
    problems = []
    for key, field in _fields(h):
        for ev in [*field.evidence, *(e for item in field.items for e in item.evidence)]:
            text = fresh[ev.doc_id].text
            span_ok = ev.char_start is not None and text[ev.char_start : ev.char_end] == ev.quote
            if not span_ok or " ".join(ev.quote.split()) not in " ".join(text.split()):
                problems.append({"field": key, "doc": ev.doc_id, "quote": ev.quote[:80]})
    for finding in h.findings:
        for ev in finding.evidence:
            text = fresh[ev.doc_id].text
            span_ok = ev.char_start is not None and text[ev.char_start : ev.char_end] == ev.quote
            if not span_ok or " ".join(ev.quote.split()) not in " ".join(text.split()):
                problems.append({"field": f"finding {finding.id}", "doc": ev.doc_id, "quote": ev.quote[:80]})
    return problems


def _leaves(value: Any, key: str = "") -> Iterator[tuple[str, Any]]:
    if isinstance(value, dict):
        for k, v in value.items():
            if k not in DERIVED_KEYS:
                yield from _leaves(v, k)
    elif isinstance(value, list):
        for v in value:
            yield from _leaves(v, key)
    elif value is not None and not isinstance(value, bool):
        yield key, value


def hallucinations(h: Handover) -> list[dict[str, Any]]:
    """Every value string/number of a field must occur in that field's own evidence quotes.

    Skipped: field 12 (document metadata rows), field 4 (checked sentence by sentence), derived keys and ISO dates
    (clinical dates are checked by the evidence lock against the quote and the document header).
    """
    out: list[dict[str, Any]] = []
    for key, field in _fields(h):
        value = getattr(field, "value", None)
        if field.status == HandoverStatus.MISSING:
            if value is not None:
                out.append({"field": key, "why": "missing field carries a value"})
            continue
        if key in ("4_epicrisis", "12_examinations") or value is None:
            continue
        quotes = " ".join(ev.quote for ev in field.evidence)
        folded, numbers = fold_text(quotes), numbers_in(quotes)
        data = value.model_dump(mode="json") if hasattr(value, "model_dump") else value
        if isinstance(data, list):
            data = [v.model_dump(mode="json") if hasattr(v, "model_dump") else v for v in data]
        for leaf_key, leaf in _leaves(data):
            if isinstance(leaf, str):
                leaf = _ATTRIBUTION.sub("", leaf)  # "Uvedeno v dokumentaci (title, date): " is metadata
                if _ISO_DATE.match(leaf) or fold_text(leaf) in folded:
                    continue
                out.append({"field": key, "key": leaf_key, "why": f"text not in evidence: {leaf[:60]}"})
            elif isinstance(leaf, int | float) and Decimal(repr(leaf)).normalize() not in numbers:
                out.append({"field": key, "key": leaf_key, "why": f"number not in evidence: {leaf}"})
    return out


def epicrisis_report(h: Handover, known: list[Fact], golden: dict[str, Any]) -> dict[str, Any]:
    field = h.fields.epicrisis
    value = field.value
    if value is None:
        return {"mode": None, "sentences": 0, "all_cited": False, "must_mention": {}}
    docs = {d: s for d, s in handover_documents().items() if d in h.included_documents}
    aliased = select_facts(known, docs)
    payload = {"sentences": [{"text": s.text, "fact_ids": s.aliases} for s in value.sentences]}
    _, problems = check_sentences(payload, aliased)
    for i, (sentence, item) in enumerate(zip(value.sentences, field.items, strict=False), start=1):
        if len(item.evidence) != len(sentence.aliases):
            problems.append(f"sentence {i}: citation legend does not match its evidence")
    text = value.text.casefold()
    mentions = {m: m.casefold() in text for m in golden["fields"]["4_epicrisis"]["must_mention"]}
    return {
        "mode": value.mode,
        "sentences": len(value.sentences),
        "all_cited": not problems and all(s.fact_ids for s in value.sentences),
        "problems": problems,
        "must_mention": mentions,
    }


# ---------------------------------------------------------------- key values vs golden


def key_values(h: Handover, golden: dict[str, Any]) -> dict[str, bool]:
    g = golden["fields"]
    f = h.fields
    patient, contacts, diagnosis = f.patient.value, f.contacts.value, f.diagnosis.value
    weights = f.weight_height.value.weights if f.weight_height.value else []
    labs = f.labs.value or []
    histology = f.histology.value
    gp = g["1_patient"]["value"]
    checks = {
        "1.birth_number": bool(patient and patient.birth_number == gp["birth_number"]),
        "1.birth_date": bool(patient and patient.birth_date.isoformat() == gp["birth_date"]),
        "1.insurer_code": bool(patient and patient.insurer_code == gp["insurer_code"]),
        "2.patient_phone": bool(contacts and contacts.patient_phone == g["2_contacts"]["value"]["patient_phone"]),
        "2.contact_person": bool(
            contacts and contacts.contact_person and contacts.contact_person.name == "Petra Horká"
        ),
        "2.email_missing": "patient_email" in f.contacts.missing,
        "3.icd10": bool(diagnosis and diagnosis.icd10 == g["3_diagnosis"]["value"]["icd10"]),
        "3.morphology": bool(diagnosis and diagnosis.icdo3_morphology == g["3_diagnosis"]["value"]["icdo3_morphology"]),
        "3.verified_on": bool(
            diagnosis
            and diagnosis.verified_histologically_on
            and diagnosis.verified_histologically_on.isoformat()
            == g["3_diagnosis"]["value"]["verified_histologically_on"]
        ),
        "3.tnm_missing": "tnm_clinical_stage" in f.diagnosis.missing,
        "7.drugs": {m.drug.casefold() for m in f.medications.value or []}
        == {m["drug"] for m in g["7_medications"]["value"]},
        "8.allergies": f.allergies.value == g["8_allergies"]["value"] or (f.allergies.value or "").endswith("neguje"),
        "9.ecog_missing_owner": f.performance_status.value is None
        and any(m.suggested_owner == "koc_physician" for m in f.performance_status.missing_items),
        "10.weight_65_stale": bool(weights)
        and (weights[-1].kg, weights[-1].date.isoformat()) == (65, "2026-09-15")
        and f.weight_height.status == HandoverStatus.STALE,
        "12.documents": {e.doc_id for e in f.examinations.value or []}
        == {e["doc"] for e in g["12_examinations"]["value"]},
        "14.report_id": bool(histology and histology.report_id == g["14_histology"]["value"]["report_id"]),
        "14.issued": bool(
            histology and histology.issued and histology.issued.isoformat() == g["14_histology"]["value"]["issued"]
        ),
        "14.ihc": bool(histology and histology.ihc == g["14_histology"]["value"]["ihc"]),
        "14.grade": bool(histology and histology.grade == g["14_histology"]["value"]["grade"]),
    }
    for kv in g["13_labs"]["key_values"]:
        checks[f"13.{kv['test']}@{kv['date']}"] = any(
            fold_text(r.test) == fold_text(kv["test"]) and r.value == kv["value"] and r.date.isoformat() == kv["date"]
            for r in labs
        )
    return checks


# ---------------------------------------------------------------- main


async def run(extraction: CompletionClient, epicrisis_client: CompletionClient) -> dict[str, Any]:
    golden = json.loads(GOLDEN.read_text(encoding="utf-8"))
    docs, facts = await extract_all(extraction)
    handover, known = await build(facts, epicrisis_client, AS_OF, docs)
    later, _ = await build(facts, epicrisis_client, LATER_AS_OF, docs)
    fresh = {p.stem: normalize(p) for p in sorted(DOCS_DIR.glob("*.docx"))}

    statuses = []
    for key, field in _fields(handover):
        expected = golden["fields"][key]["status"]
        statuses.append(
            {"field": key, "expected": expected, "predicted": str(field.status), "ok": expected == field.status}
        )
    correct = sum(1 for s in statuses if s["ok"])

    excluded = {e["doc"] for e in golden["excluded_documents"]}
    leakage = sorted(
        {ev.doc_id for _, field in _fields(handover) for ev in field.evidence if ev.doc_id in excluded}
        | ({e.doc_id for e in handover.fields.examinations.value or []} & excluded)
        | ({r.doc_id for r in handover.fields.labs.value or []} & excluded)
        | (set(handover.included_documents) & excluded)
        | ({ev.doc_id for x in handover.findings for ev in x.evidence} & excluded)
        | ({d for x in handover.findings for d in x.docs} & excluded)
    )
    evidence_bad = evidence_problems(handover, fresh)
    halluc = hallucinations(handover)
    items_bad = item_problems(handover)
    epicrisis = epicrisis_report(handover, known, golden)
    kv = key_values(handover, golden)
    evidence_total = sum(
        len(field.evidence) + sum(len(i.evidence) for i in field.items) for _, field in _fields(handover)
    ) + sum(len(x.evidence) for x in handover.findings)
    as_of_rule = {
        "excluded_at_2026-10-21": sorted(e.doc_id for e in handover.excluded_documents),
        "excluded_at_2026-10-28": sorted(e.doc_id for e in later.excluded_documents),
        "ok": {e.doc_id for e in handover.excluded_documents} == excluded
        and not later.excluded_documents
        and excluded <= set(later.included_documents),
    }
    return {
        "as_of": AS_OF.isoformat(),
        "metrics": {
            "field_status_accuracy": f"{correct}/{len(statuses)}",
            "field_status_correct": correct,
            "evidence_items": evidence_total,
            "evidence_validity": round(1 - len(evidence_bad) / evidence_total, 4) if evidence_total else None,
            "as_of_leakage": len(leakage),
            "hallucinations": len(halluc),
            "key_values": f"{sum(kv.values())}/{len(kv)}",
            "epicrisis_mode": epicrisis["mode"],
            "epicrisis_all_cited": epicrisis["all_cited"],
            "negated_values_repaired": sum(1 for f in known if NEGATED_VALUE_REPAIRED in f.lock_notes),
        },
        "gates": {
            f"field_status_ge_{FIELD_STATUS_GATE}": correct >= FIELD_STATUS_GATE,
            "evidence_validity_100": evidence_total > 0 and not evidence_bad,
            "as_of_leakage_0": not leakage,
            "hallucinations_0": not halluc,
            "epicrisis_cited": epicrisis["all_cited"],
            "items_with_evidence": not items_bad,
            "as_of_rule": as_of_rule["ok"],
        },
        "field_status": statuses,
        "key_value_checks": kv,
        "as_of_rule": as_of_rule,
        "epicrisis": epicrisis,
        "evidence_problems": evidence_bad,
        "hallucination_details": halluc,
        "item_problems": items_bad,
        "leakage_docs": leakage,
        "handover": handover.model_dump(mode="json", by_alias=True),
    }


def format_table(rep: dict[str, Any]) -> str:
    m, g = rep["metrics"], rep["gates"]
    rows = [
        ("Field status accuracy", m["field_status_accuracy"], f"gate ≥ {FIELD_STATUS_GATE}/15"),
        ("Evidence validity", m["evidence_validity"], f"gate 100 % ({m['evidence_items']} quotes)"),
        ("As-of leakage", m["as_of_leakage"], "gate 0"),
        ("Hallucinations", m["hallucinations"], "gate 0"),
        ("Key values", m["key_values"], "info"),
        ("Epicrisis", f"{m['epicrisis_mode']}, cited={m['epicrisis_all_cited']}", "gate: every sentence cited"),
        ("Negated values from quote", m["negated_values_repaired"], "lock repair, audit"),
    ]
    lines = ["Štafeta handover eval (as of 2026-10-21 08:00)"]
    lines += [f"  {name:<34} {val!s:<22} {note}" for name, val, note in rows]
    lines += [
        f"  STATUS {s['field']}: expected {s['expected']}, got {s['predicted']}"
        for s in rep["field_status"]
        if not s["ok"]
    ]
    lines += [f"  KEY VALUE MISS: {k}" for k, ok in rep["key_value_checks"].items() if not ok]
    lines += [f"  HALLUCINATION: {h}" for h in rep["hallucination_details"]]
    if rep["epicrisis"]["mode"] == "fallback":
        lines.append("  Epicrisis: fallback (no cached LLM answer; a human runs `STAFETA_LLM_CACHE=0 make eval`)")
    lines.append("  As-of 12/13: " + json.dumps(rep["as_of_rule"], ensure_ascii=False))
    lines.append("  Gates: " + ", ".join(f"{k}={'PASS' if v else 'FAIL'}" for k, v in g.items()))
    return "\n".join(lines)


def merge_into_report(rep: dict[str, Any]) -> None:
    """Add the handover section to eval/report.json (written by the extraction eval in the same run)."""
    REPORT.parent.mkdir(parents=True, exist_ok=True)
    current: dict[str, Any] = json.loads(REPORT.read_text(encoding="utf-8")) if REPORT.exists() else {}
    current["handover"] = rep
    current.setdefault("metrics", {})["field_status_accuracy"] = rep["metrics"]["field_status_accuracy"]
    REPORT.write_text(json.dumps(current, ensure_ascii=False, indent=1), encoding="utf-8")
