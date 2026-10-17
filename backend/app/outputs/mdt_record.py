"""MDT record (zápis z jednání MDT) as DOCX in the layout of `data/raw/MDT_zapis.docx`.

Content comes ONLY from the handover as of the MDT start (confirmed or draft sections, findings, the list of excluded
documents) and from directory facts about the referring doctor. Nothing is added: what the sources do not state is
"Chybí"; sections 6 (Závěr MDT) and 7 (Doporučení MDT) are left for the physicians to write at the meeting; the system
never drafts a conclusion or a recommendation. Every section carries a label of its review status:

- "Potvrzeno lékařem (kdo, kdy)"              the KOC physician confirmed the section (Provenance in FHIR)
- "Částečně potvrzeno lékařem"                some of the section's source fields are confirmed, the rest are named
- "Návrh AI – čeká na potvrzení lékařem"      assembled from the documents, not yet confirmed
- "Chybí"                                      the documents do not state it

Under each label the section's notes and missing items are printed, so a value is never shown without what is known to
be uncertain about it. All text that reaches the document is sanitised first (XML-illegal characters, layout control
characters, birth numbers), the Jinja environment is sandboxed and the rendered file is checked for completeness.

The template `templates/mdt_zapis.docx` is built from the sample form by `python -m app.outputs.build_template`.
"""

from __future__ import annotations

import html
import io
import re
import zipfile
from dataclasses import dataclass
from datetime import date, datetime
from pathlib import Path
from typing import Any, Final

from docxtpl import DocxTemplate, RichText  # type: ignore[import-untyped]
from jinja2.sandbox import SandboxedEnvironment

from app.domain.handover import (
    Handover,
    HandoverFieldBase,
    HandoverItem,
    HandoverStatus,
    ReviewState,
)
from app.settings import PRAGUE

TEMPLATE: Final = Path(__file__).parent / "templates" / "mdt_zapis.docx"
DOCX_MEDIA_TYPE: Final = "application/vnd.openxmlformats-officedocument.wordprocessingml.document"

LABEL_CONFIRMED: Final = "Potvrzeno lékařem"
LABEL_CONFIRMED_EDITED: Final = "Potvrzeno lékařem (upraveno lékařem)"
LABEL_PARTIAL: Final = "Částečně potvrzeno lékařem"
LABEL_ACCEPTED_MISSING: Final = "Chybí – lékař potvrdil, že zůstává chybějící"
LABEL_DRAFT: Final = "Návrh AI – čeká na potvrzení lékařem"
LABEL_MISSING: Final = "Chybí"
MISSING_TEXT: Final = "Chybí"
FOR_PHYSICIANS: Final = "Vyplní lékař na jednání MDT. Systém závěr ani doporučení nevytváří."
NO_MEMBERS: Final = "Chybí – prezence členů MDT není v systému zaznamenána."
BANNER_DRAFT: Final = "NÁVRH – zápis obsahuje oddíly, které lékař dosud nepotvrdil (viz označení oddílů)."
BANNER_FINAL: Final = "Podklady sestavil systém Štafeta z dokumentace; všechny oddíly předávky potvrdil lékař."
PAGE_BANNER_DRAFT: Final = "NÁVRH – obsahuje oddíly nepotvrzené lékařem"
REDACTED_BIRTH_NUMBER: Final = "[RČ vynecháno]"
RED: Final = "C00000"
GREY: Final = "595959"

_STATUS_NOTES: Final = {
    HandoverStatus.STALE: "neaktuální údaj",
    HandoverStatus.NEEDS_CLARIFICATION: "k upřesnění",
}
_FIELD_TITLES: Final = {
    "patient": "Nacionále",
    "contacts": "Kontakty",
    "weight_height": "Váha a výška",
    "diagnosis": "Diagnóza",
    "comorbidities": "Komorbidity",
    "examinations": "Vyšetření",
    "labs": "Laboratoř",
    "histology": "Histologie",
}
# Czech names of the handover's missing-item keys (never show the internal key).
_MISSING_LABELS: Final = {
    "name_or_birth_date": "jméno nebo datum narození",
    "birth_number": "rodné číslo",
    "insurer_code": "kód pojišťovny",
    "address": "adresa",
    "patient_phone": "telefon pacienta",
    "patient_email": "e-mail pacienta",
    "contact_person": "kontaktní osoba",
    "diagnosis": "diagnóza",
    "icd10": "kód MKN-10",
    "histology": "histologie",
    "tnm_clinical_stage": "TNM klinické stadium",
    "mdt_question": "požadavek na MDT",
    "explicit_mdt_question": "konkrétní otázka pro MDT",
    "comorbidities": "komorbidity",
    "medications": "léková anamnéza",
    "allergies": "alergie",
    "ecog": "ECOG / Karnofsky",
    "current_weight": "aktuální hmotnost",
    "weight": "hmotnost",
    "height": "výška",
    "symptoms": "symptomy",
    "examinations": "vyšetření",
    "labs": "laboratoř",
    "other": "jiná sdělení",
}
# The handover sections that have no place in the MDT_zapis form; listed in appendix C.
_APPENDIX_FIELDS: Final = (
    ("epicrisis", "Epikríza"),
    ("mdt_question", "Požadavek / otázka na MDT"),
    ("medications", "Léková anamnéza (FA)"),
    ("allergies", "Alergie (AA)"),
    ("performance_status", "PS / Karnofsky"),
    ("symptoms", "Symptomy a jejich počátek"),
    ("other", "Jiná důležitá sdělení"),
)
_ONSET_LABEL: Final = "Počátek obtíží"  # documented as free text ("od poloviny srpna"): no day-exact date is printed
_MULTILINE_KEYS: Final = frozenset({"patient_lines", "referring_lines", "comorbidities_text", "diagnosis_name"})

_XML_ILLEGAL: Final = re.compile("[^\\u0009\\u000a\\u000d\\u0020-\\ud7ff\\ue000-\\ufffd\\U00010000-\\U0010ffff]")
_LAYOUT_CONTROL: Final = re.compile("[\\a\\f\\v\\t]")
_BIRTH_NUMBER: Final = re.compile(r"\b\d{6}/\d{3,4}\b")
_EXCLUSION_TIMESTAMP: Final = re.compile(r"\s*\(\d{4}-\d{2}-\d{2}T[^)]*\)")
_TEXT_RUN: Final = re.compile(r"<w:t(?:\s[^>]*)?>([^<]*)</w:t>")


class MdtRecordError(RuntimeError):
    """The rendered document is incomplete; never hand a truncated clinical document to a user."""


@dataclass(frozen=True)
class ReferringDoctor:
    """The referring GP as the directory knows them (not part of the handover)."""

    name: str | None
    phone: str | None = None
    email: str | None = None


# --- labels ----------------------------------------------------------------------------------------------------------


def field_label(field: HandoverFieldBase) -> str:
    review = field.review
    if review is not None and review.state is ReviewState.CONFIRMED:
        return LABEL_CONFIRMED_EDITED if review.edited else LABEL_CONFIRMED
    if review is not None and review.state is ReviewState.ACCEPTED_MISSING:
        return LABEL_ACCEPTED_MISSING
    if field.status is HandoverStatus.MISSING:
        return LABEL_MISSING
    return LABEL_DRAFT


def is_reviewed(field: HandoverFieldBase) -> bool:
    return field.review is not None and field.review.state in (ReviewState.CONFIRMED, ReviewState.ACCEPTED_MISSING)


def is_draft(handover: Handover) -> bool:
    """True while any of the 15 sections is not confirmed (or accepted as missing) by a physician."""
    return not all(is_reviewed(f) for f in _all_fields(handover))


def _attestation(field: HandoverFieldBase) -> str | None:
    review = field.review
    if review is None or review.by is None or review.at is None or not is_reviewed(field):
        return None
    at = review.at.astimezone(PRAGUE)
    return f"{_line(review.by.display)}, {_cz_date(at)} {at:%H:%M}"


def section_label(fields: list[tuple[str, HandoverFieldBase]], *, note: str | None = None) -> RichText:
    """Bold review label (who/when for confirmed sections) and, below it in grey, every note, conflict and missing item
    of the source fields. `fields` are (title, field) pairs; titles prefix the notes of multi-field sections."""
    labels = list(dict.fromkeys(field_label(f) for _, f in fields))
    attested = list(dict.fromkeys(a for _, f in fields if (a := _attestation(f))))
    detail = ""
    if len(labels) == 1:
        head = labels[0]
        if attested:
            head += f" ({'; '.join(attested)})"
    elif any(is_reviewed(f) for _, f in fields):
        head = LABEL_PARTIAL + (f" ({'; '.join(attested)})" if attested else "")
        detail = "nepotvrzeno: " + ", ".join(t for t, f in fields if not is_reviewed(f))
    else:
        head = LABEL_DRAFT
        detail = "chybí: " + ", ".join(t for t, f in fields if f.status is HandoverStatus.MISSING)
    lines: list[str] = []
    for title, field in fields:
        prefix = f"{title}: " if len(fields) > 1 else ""
        if field.conflicts:
            lines.append(f"{prefix}nesoulad: {', '.join(field.conflicts)}")
        if field.status in _STATUS_NOTES:
            lines.append(f"{prefix}{_STATUS_NOTES[field.status]}")
        lines += [f"{prefix}{_missing_line(m.item, m.reason)}" for m in field.missing_items]
        if field.note:
            lines.append(f"{prefix}{_line(field.note)}")
    if note:
        lines.append(note)
    text = RichText()
    text.add(head, bold=True)
    if detail:
        text.add(f" – {detail}")
    for line in dict.fromkeys(_line(x) for x in lines):
        text.add("\n" + line, italic=True, color=GREY)
    return text


# --- context ---------------------------------------------------------------------------------------------------------


def build_context(handover: Handover, referring: ReferringDoctor | None, generated_at: datetime) -> dict[str, Any]:
    f = handover.fields
    patient, contacts, weight = f.patient.value, f.contacts.value, f.weight_height
    as_of = handover.as_of.astimezone(PRAGUE)
    mdt_text = f"{_cz_date(as_of)} {as_of:%H:%M}"

    insurer = MISSING_TEXT
    if patient is not None and patient.insurer_code:
        insurer = f"{patient.insurer_code} – {patient.insurer_name}" if patient.insurer_name else patient.insurer_code
    patient_lines = [
        "",
        f"{patient.given} {patient.family}" if patient else MISSING_TEXT,
        insurer,
        _contact(contacts.patient_phone if contacts else None, contacts.patient_email if contacts else None),
        (patient.address if patient and patient.address else MISSING_TEXT),
        "; ".join(_item_text(i) for i in weight.items) or MISSING_TEXT,
    ]
    referring_lines = [
        "",
        (referring.name if referring and referring.name else MISSING_TEXT),
        _contact(referring.phone if referring else None, referring.email if referring else None),
    ]
    draft = is_draft(handover)
    banner = RichText()
    banner.add(BANNER_DRAFT if draft else BANNER_FINAL, bold=True, color=RED if draft else None)
    page_banner = RichText()
    if draft:
        page_banner.add(PAGE_BANNER_DRAFT, bold=True, color=RED)
    generated = generated_at.astimezone(PRAGUE)
    context: dict[str, Any] = {
        "banner": banner,
        "page_banner": page_banner,
        "meta": (
            f"Stav podkladů k {mdt_text}. "
            f"Zahrnuto dokumentů: {len(handover.included_documents)}, nezahrnuto: {len(handover.excluded_documents)}."
        ),
        "s1": section_label(
            _titled(handover, "patient", "contacts", "weight_height"),
            note="Datum MDT je z případu, referující lékař z adresáře Štafety (nejsou součástí předávky).",
        ),
        "s2": _plain(NO_MEMBERS),
        "s3": section_label(_titled(handover, "diagnosis")),
        "s4": section_label(_titled(handover, "comorbidities")),
        "s5": section_label(_titled(handover, "examinations", "labs", "histology")),
        "s6": _plain(FOR_PHYSICIANS),
        "s7": _plain(FOR_PHYSICIANS),
        "mdt_date": mdt_text,
        "patient_lines": "\n".join(patient_lines),
        "referring_lines": "\n".join(referring_lines),
        "diagnosis_name": _diagnosis_name(handover),
        "diagnosis_code": _diagnosis_code(handover),
        "comorbidities_text": _comorbidities(handover),
        "results": _results(handover),
        "findings": [_finding_line(x) for x in handover.findings] or ["Žádné záznamy."],
        "excluded": [_excluded_line(x.doc_id, x.reason, mdt_text) for x in handover.excluded_documents] or ["Žádné."],
        "appendix": [_appendix_section(handover, key, title) for key, title in _APPENDIX_FIELDS],
        "footer": (
            f"Zápis vygeneroval systém Štafeta (prototyp, fiktivní data) dne {_cz_date(generated)} "
            f"{generated:%H:%M}. Systém nevytváří závěr ani doporučení MDT."
        ),
    }
    return _sanitise(context)


def render_mdt_record(handover: Handover, referring: ReferringDoctor | None, generated_at: datetime) -> bytes:
    context = build_context(handover, referring, generated_at)
    template = DocxTemplate(str(TEMPLATE))
    template.render(context, jinja_env=SandboxedEnvironment(autoescape=True))
    buffer = io.BytesIO()
    template.save(buffer)
    data = buffer.getvalue()
    _verify_complete(data, context["footer"])
    return data


def _verify_complete(data: bytes, footer: str) -> None:
    """The last paragraph must be there: a broken value could otherwise silently cut the document short."""
    with zipfile.ZipFile(io.BytesIO(data)) as package:
        xml = package.read("word/document.xml").decode("utf-8")
    text = html.unescape("".join(_TEXT_RUN.findall(xml)))
    if footer not in text:
        raise MdtRecordError("the rendered MDT record is incomplete")


# --- section builders ------------------------------------------------------------------------------------------------


def _all_fields(handover: Handover) -> list[HandoverFieldBase]:
    return [getattr(handover.fields, name) for name in type(handover.fields).model_fields]


def _titled(handover: Handover, *names: str) -> list[tuple[str, HandoverFieldBase]]:
    return [(_FIELD_TITLES[n], getattr(handover.fields, n)) for n in names]


def _docs(field: HandoverFieldBase) -> str:
    docs = sorted({e.doc_id for e in field.evidence})
    return f" [{', '.join(docs)}]" if docs else ""


def _diagnosis_name(handover: Handover) -> str:
    field = handover.fields.diagnosis
    diagnosis = field.value
    if diagnosis is None:
        return MISSING_TEXT
    lines = [f"{diagnosis.text}{_docs(field)}"]
    if diagnosis.icdo3_morphology:
        lines.append(f"Morfologie (ICD-O-3): {diagnosis.icdo3_morphology}")
    if diagnosis.verified_histologically_on:
        lines.append(f"Histologicky ověřeno: {_cz_date(diagnosis.verified_histologically_on)}")
    if diagnosis.tnm:
        lines.append(f"TNM: {diagnosis.tnm}")
    return "\n".join(lines)


def _diagnosis_code(handover: Handover) -> str:
    field = handover.fields.diagnosis
    if field.value is None or not field.value.icd10:
        return MISSING_TEXT
    return f"{field.value.icd10}{_docs(field)}"


def _comorbidities(handover: Handover) -> str:
    field = handover.fields.comorbidities
    lines = []
    for item in field.value or []:
        code = f" ({item.icd10})" if item.icd10 else ""
        detail = f" – {item.detail}" if item.detail else ""
        lines.append(f"{item.text}{code}{detail}")
    if lines:
        return "\n".join([*lines, f"Zdroj:{_docs(field)}"]) if field.evidence else "\n".join(lines)
    return f"{MISSING_TEXT} – v dokumentaci neuvedeno" if field.status is HandoverStatus.MISSING else "Neuvedeno"


def _results(handover: Handover) -> list[dict[str, str]]:
    """Examinations, lab results and the histology as table rows (date, examination, result), oldest first.

    The values of one laboratory report share one row (with its report when the report is also listed as an
    examination), so a report with dozens of values stays readable; nothing is dropped or rounded.
    """
    f = handover.fields
    labs_by_report: dict[str, list[Any]] = {}
    for lab in f.labs.value or []:
        labs_by_report.setdefault(lab.doc_id, []).append(lab)
    rows: list[tuple[date | None, str, str]] = []
    for exam in f.examinations.value or []:
        values = labs_by_report.pop(exam.doc_id, [])
        result = _lab_values(values, exam.doc_id) if values else f"Viz zpráva [{exam.doc_id}]"
        rows.append((exam.date, f"{exam.type} – {exam.place}", result))
    for doc_id, values in labs_by_report.items():  # laboratory values whose report is not listed as an examination
        rows.append((min(v.date for v in values), "Laboratorní výsledky", _lab_values(values, doc_id)))
    histology = f.histology.value
    if histology is not None:
        parts = []
        if histology.grade:
            parts.append(f"grade {histology.grade}")
        if histology.perineural_invasion is not None:
            parts.append("perineurální invaze: " + ("ano" if histology.perineural_invasion else "ne"))
        if histology.ihc:
            parts.append("IHC: " + ", ".join(f"{k} {v}" for k, v in histology.ihc.items()))
        source = _docs(f.histology)
        title = "Histologie" + (f" ({histology.report_id})" if histology.report_id else "")
        rows.append((histology.issued, title, "; ".join(parts) + source if parts else f"Viz zpráva{source}"))
    rows.sort(key=lambda r: (r[0] is None, r[0] or date.min))
    return [{"date": _cz_date(d) if d else "", "exam": exam, "result": result} for d, exam, result in rows]


def _lab_values(values: list[Any], doc_id: str) -> str:
    parts = []
    for lab in values:
        unit = f" {lab.unit}" if lab.unit and lab.unit != "1" else ""  # "1" = dimensionless: "0,37 1" reads as 0,371
        flag = f" ({lab.flag})" if lab.flag else ""
        parts.append(f"{lab.test} {_number(lab.value)}{unit}{flag}")
    return "; ".join(parts) + f" [{doc_id}]"


def _finding_line(finding: Any) -> str:
    docs = f" (dokumenty: {', '.join(finding.docs)})" if finding.docs else ""
    return f"{finding.id} · {finding.message}{docs}"


def _excluded_line(doc_id: str, reason: str, mdt_text: str) -> str:
    after_mdt = reason.startswith(("vytvořeno", "doručeno po"))
    shown = _EXCLUSION_TIMESTAMP.sub("", reason).replace("as_of", "začátku MDT")
    if after_mdt:
        return f"{doc_id} – po MDT ({shown}; začátek MDT {mdt_text})"
    return f"{doc_id} – nezahrnuto ({shown})"


def _appendix_section(handover: Handover, key: str, title: str) -> dict[str, Any]:
    field: HandoverFieldBase = getattr(handover.fields, key)
    lines: list[str] = []
    if key == "epicrisis" and not field.items:
        value = handover.fields.epicrisis.value
        lines.append(value.text if value else MISSING_TEXT)
    else:
        onset = handover.fields.symptoms.value.onset if handover.fields.symptoms.value else None
        lines.extend(_item_text(i, with_date=not (key == "symptoms" and _is_onset(i, onset))) for i in field.items)
    lines.extend(_missing_line(m.item, m.reason) for m in field.missing_items)
    if field.note:
        lines.append("Poznámka: " + _reword_note(field.note))
    attested = _attestation(field)
    heading = RichText()
    heading.add(f"{title} – ", bold=True)
    heading.add(field_label(field) + (f" ({attested})" if attested else ""), bold=True)
    return {"title": heading, "lines": lines or [MISSING_TEXT]}


# --- small helpers ---------------------------------------------------------------------------------------------------


def _is_onset(item: HandoverItem, onset: str | None) -> bool:
    """The onset is documented as free text ("od poloviny srpna"); a day-exact date next to it would be invented."""
    value = str(item.value)
    return item.label == _ONSET_LABEL or bool(onset and (onset in value or value in onset))


def _plain(text: str) -> RichText:
    rich = RichText()
    rich.add(text, italic=True, color=GREY)
    return rich


def _contact(phone: str | None, email: str | None) -> str:
    return f"Telefon: {phone or 'chybí'} · e-mail: {email or 'chybí'}"


def _missing_line(item: str, reason: str) -> str:
    return f"Chybí: {_MISSING_LABELS.get(item, item.replace('_', ' '))} – {reason}"


def _reword_note(note: str) -> str:
    if note.startswith("Souhrn AI není k dispozici"):
        return "Souhrn AI nebyl vytvořen; níže je přehled citovaných údajů z dokumentace."
    return note


def _item_text(item: HandoverItem, *, with_date: bool = True) -> str:
    value = _number(item.value) if isinstance(item.value, float) else str(item.value)
    label = f"{item.label}: " if item.label else ""
    unit = f" {item.unit}" if item.unit and item.unit != "1" else ""
    when = f" ({_cz_date(item.clinical_date)})" if item.clinical_date and with_date else ""
    docs = sorted({e.doc_id for e in item.evidence})
    source = f" [{', '.join(docs)}]" if docs else ""
    return f"{label}{value}{unit}{when}{source}"


def _number(value: float) -> str:
    """Full precision with a Czech decimal comma (never rounded)."""
    return str(int(value)) if float(value).is_integer() else repr(float(value)).replace(".", ",")


def _cz_date(day: date | datetime) -> str:
    return f"{day.day}. {day.month}. {day.year}"


# --- sanitising ------------------------------------------------------------------------------------------------------


def _clean(text: str, *, multiline: bool) -> str:
    """Make a value safe for the document: no XML-illegal characters or lone surrogates (they would truncate the
    file), no layout control characters (paragraph or page breaks), no birth numbers, no line breaks unless allowed."""
    text = _LAYOUT_CONTROL.sub(" ", text)
    text = _XML_ILLEGAL.sub("", text.replace("\r\n", "\n").replace("\r", "\n"))
    if not multiline:
        text = text.replace("\n", " ")
    return _BIRTH_NUMBER.sub(REDACTED_BIRTH_NUMBER, text)


def _line(text: str) -> str:
    return _clean(text, multiline=False)


def _sanitise(context: dict[str, Any]) -> dict[str, Any]:
    """Clean every plain string of the context; RichText parts are cleaned where they are built."""
    result: dict[str, Any] = {}
    for key, value in context.items():
        multiline = key in _MULTILINE_KEYS
        if isinstance(value, str):
            result[key] = _clean(value, multiline=multiline)
        elif isinstance(value, list):
            result[key] = [_sanitise_item(v) for v in value]
        else:
            result[key] = value
    return result


def _sanitise_item(value: Any) -> Any:
    if isinstance(value, str):
        return _clean(value, multiline=False)
    if isinstance(value, dict):
        return {k: _sanitise_item(v) for k, v in value.items()}
    if isinstance(value, list):
        return [_sanitise_item(v) for v in value]
    return value
