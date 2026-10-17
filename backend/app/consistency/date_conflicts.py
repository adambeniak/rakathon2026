"""Deterministic date-conflict rules over the accepted, quoted facts of a handover (no LLM, no clinical judgement).

C1  drug pause vs procedure date: a quote gives the "last dose" of a drug after the procedure date of the same
    document (handover field 7). A quote of the same document that names the drug and a "resume from" date is
    shown verbatim as context.
C2  specimen date vs report date: the specimen collection ("odběr") is after the report's issue date ("Datum vydání")
    in the same document (handover field 14; field 3 shows the same issue date as the verification date, see
    `RELATED_FIELDS`). For a pathology report the deterministically parsed header lines decide
    (`app.extraction.handover.headers`, whole quoted lines), so the rule does not depend on the model having
    extracted the issue date as a fact; otherwise the quoted facts are used. Procedure dates stated in other
    documents are shown verbatim for comparison.

Only `stated` facts trigger a rule, and only dates with an explicit year that directly follow the cue phrase in the
quote are read (labels in the model's value are not trusted), so nothing is guessed. The input must
already be filtered by the as-of rule. Messages quote the source instead of paraphrasing it and never say which side is
right or what should be done. A second conflict of the same kind gets the id `C1-2`, `C1-3`, … (the first is `C1`).
"""

from __future__ import annotations

import re
from collections.abc import Mapping, Sequence
from datetime import date
from typing import Final

from app.documents.doc_type import PATHOLOGY
from app.documents.normalize import find_dates
from app.domain.evidence import Certainty, Evidence, Fact, FactType
from app.domain.finding import Finding, FindingKind, Severity
from app.extraction.handover.headers import DocumentHeader, is_pathology_report

C1_FIELD = "7_medications"
C2_FIELD = "14_histology"
# Fields that show a finding's anchor date without being its primary field: the finding id is recorded on them when
# their evidence cites the same quote (no status change; `assemble.apply_findings`).
RELATED_FIELDS: Final[Mapping[str, tuple[str, ...]]] = {C2_FIELD: ("3_diagnosis",)}
VERIFY_ACTION = "flag_and_create_verification_task"

_PROCEDURE_DATE_LABEL = "datum výkonu"
_ISSUE_DATE_LABEL = "datum vydání"
_DATE = r"(\d{1,2}\.\s*\d{1,2}\.\s*\d{4})"
_LAST_DOSE = re.compile(rf"poslední\s+dávk\w*\s+(?:dne\s+)?{_DATE}", re.IGNORECASE)
_RESUME = re.compile(rf"znovu\s+od\s+{_DATE}", re.IGNORECASE)
_SPECIMEN = re.compile(rf"\bodběr:?\s+(?:dne\s+)?{_DATE}", re.IGNORECASE)


def detect_findings(
    facts: Sequence[Fact],
    headers: Mapping[str, DocumentHeader] | None = None,
    type_codes: Mapping[str, str | None] | None = None,
) -> list[Finding]:
    """All C1 and C2 findings for already as-of-filtered facts and header lines, in doc_id order.

    `headers` (doc_id -> parsed header) and `type_codes` (doc_id -> LOINC document type) must cover the same
    as-of-included documents as `facts`.
    """
    ordered = sorted(facts, key=lambda f: f.doc_id)
    c2 = _specimen_vs_report(ordered, headers or {}, type_codes or {})
    return [*_numbered("C1", _drug_pause_vs_procedure(ordered)), *_numbered("C2", c2)]


def _numbered(base: str, findings: Sequence[Finding]) -> list[Finding]:
    return [f.model_copy(update={"id": base if i == 0 else f"{base}-{i + 1}"}) for i, f in enumerate(findings)]


def _doc_no(doc_id: str) -> str:
    return doc_id.split("_", 1)[0]


def _quote(fact: Fact) -> str:
    return fact.evidence[0].quote


def _cited(fact: Fact | Evidence) -> str:
    return f"„{fact.quote if isinstance(fact, Evidence) else _quote(fact)}“"


def _anchor_date(fact: Fact, label: str) -> date | None:
    """The date of a stated `admin_date` fact, read from its quote ("<label>: <d. m. yyyy>"), not from its label."""
    if fact.type is not FactType.ADMIN_DATE or fact.certainty is not Certainty.STATED:
        return None
    m = re.search(rf"{re.escape(label)}\s*:?\s*{_DATE}", _quote(fact), re.IGNORECASE)
    dates = find_dates(m.group(1)) if m else []
    return dates[0] if dates else None


def _quoted_date(pattern: re.Pattern[str], fact: Fact) -> date | None:
    """The explicit-year date that directly follows the cue phrase in the fact's quote."""
    m = pattern.search(_quote(fact))
    if m is None:
        return None
    dates = find_dates(m.group(1))
    return dates[0] if dates else None


def _drug_name(fact: Fact) -> str | None:
    value = fact.value
    drug = value.get("drug") if isinstance(value, dict) else None
    return drug.casefold() if isinstance(drug, str) and drug.strip() else None


def _finding(kind_id: str, field: str, message: str, used: Sequence[Fact | Evidence]) -> Finding:
    evidence = [u if isinstance(u, Evidence) else u.evidence[0] for u in used]
    return Finding(
        id=kind_id,
        kind=FindingKind.DATE_CONFLICT,
        severity=Severity.HIGH,
        message=message,
        field=field,
        docs=sorted({e.doc_id for e in evidence}),
        evidence=evidence,
        suggested_action=VERIFY_ACTION,
    )


def _drug_pause_vs_procedure(facts: Sequence[Fact]) -> list[Finding]:
    found: list[Finding] = []
    for procedure in facts:
        procedure_date = _anchor_date(procedure, _PROCEDURE_DATE_LABEL)
        if procedure_date is None:
            continue
        same_doc = [f for f in facts if f.doc_id == procedure.doc_id]
        for dose in same_doc:
            if dose.type is not FactType.MEDICATION or dose.certainty is not Certainty.STATED:
                continue
            last_dose = _quoted_date(_LAST_DOSE, dose)
            if last_dose is None or last_dose <= procedure_date:
                continue
            drug = _drug_name(dose)
            resume = next(
                (
                    f
                    for f in same_doc
                    if f.type is FactType.DOCUMENTED_PLAN
                    and drug is not None
                    and drug in _quote(f).casefold()
                    and _quoted_date(_RESUME, f) is not None
                ),
                None,
            )
            used = [procedure, dose] + ([resume] if resume is not None else [])
            message = f"Nesoulad mezi {_cited(procedure)} a {_cited(dose)} (dok. {_doc_no(procedure.doc_id)})." + (
                f" V téže dokumentaci uvedeno: {_cited(resume)}" if resume is not None else ""
            )
            found.append(_finding("C1", C1_FIELD, message, used))
    return found


def _procedures(facts: Sequence[Fact], headers: Mapping[str, DocumentHeader], exclude: str) -> list[Fact | Evidence]:
    """Quoted procedure dates ("Datum výkonu: …") of the other documents: header line, else the stated fact."""
    by_doc: dict[str, Fact | Evidence] = {
        doc_id: h.procedure.evidence for doc_id, h in headers.items() if h.procedure is not None and doc_id != exclude
    }
    for f in facts:
        if f.doc_id != exclude and f.doc_id not in by_doc and _anchor_date(f, _PROCEDURE_DATE_LABEL):
            by_doc[f.doc_id] = f
    return [by_doc[d] for d in sorted(by_doc)]


def _c2(sample: Fact | Evidence, issue: Fact | Evidence, procedures: Sequence[Fact | Evidence]) -> Finding:
    doc_id = issue.doc_id
    message = f"Nesoulad mezi {_cited(sample)} a {_cited(issue)} (dok. {_doc_no(doc_id)})." + "".join(
        f" Pro srovnání: v dok. {_doc_no(p.doc_id)} uvedeno {_cited(p)}." for p in procedures
    )
    return _finding("C2", C2_FIELD, message, [sample, issue, *procedures])


def _specimen_vs_report(
    facts: Sequence[Fact], headers: Mapping[str, DocumentHeader], type_codes: Mapping[str, str | None]
) -> list[Finding]:
    found: dict[str, list[Finding]] = {}
    seen: set[tuple[str, date, date]] = set()  # (document, specimen date, issue date)
    # Pathology reports: the header issue date is the anchor (whole quoted line, explicit year), compared with the
    # header specimen line, else with the specimen dates quoted in that report's facts.
    for doc_id in sorted(headers):
        h = headers[doc_id]
        if h.issued is None or not is_pathology_report(h, type_codes.get(doc_id)):
            continue
        issued = h.issued
        samples: list[tuple[date, Fact | Evidence]] = (
            [(max(h.specimen.dates), h.specimen.evidence)]
            if h.specimen is not None
            else [(d, f) for f in facts if f.doc_id == doc_id and (d := _specimen_date(f)) is not None]
        )
        for specimen_date, sample in samples:
            if specimen_date > issued.date and (doc_id, specimen_date, issued.date) not in seen:
                seen.add((doc_id, specimen_date, issued.date))
                found.setdefault(doc_id, []).append(_c2(sample, issued.evidence, _procedures(facts, headers, doc_id)))
    # Quoted facts (the model extracted both dates); a pair already reported from the header is not repeated, and a
    # document typed as something other than pathology is never compared (the finding belongs to field 14).
    for issue in facts:
        issue_date = _anchor_date(issue, _ISSUE_DATE_LABEL)
        type_code = type_codes.get(issue.doc_id)
        if issue_date is None or (type_code is not None and type_code != PATHOLOGY):
            continue
        for sample in (f for f in facts if f.doc_id == issue.doc_id and f is not issue):
            quoted = _specimen_date(sample)
            if quoted is None or quoted <= issue_date or (issue.doc_id, quoted, issue_date) in seen:
                continue
            seen.add((issue.doc_id, quoted, issue_date))
            found.setdefault(issue.doc_id, []).append(_c2(sample, issue, _procedures(facts, headers, issue.doc_id)))
    return [f for doc_id in sorted(found) for f in found[doc_id]]


def _specimen_date(fact: Fact) -> date | None:
    return _quoted_date(_SPECIMEN, fact) if fact.certainty is Certainty.STATED else None
