"""Deterministic date-conflict rules over the accepted, quoted facts of a handover (no LLM, no clinical judgement).

C1  drug pause vs procedure date: a quote gives the "last dose" of a drug after the procedure date of the same
    document (handover field 7). A quote of the same document that names the drug and a "resume from" date is
    shown verbatim as context.
C2  specimen date vs report date: a quote gives the specimen collection ("odběr") after the report's issue date
    ("Datum vydání") in the same document (handover field 14). Procedure dates stated in other documents are shown
    verbatim for comparison.

Only `stated` facts trigger a rule, and only dates with an explicit year that directly follow the cue phrase in the
quote are read (labels in the model's value are not trusted), so nothing is guessed. The input must
already be filtered by the as-of rule. Messages quote the source instead of paraphrasing it and never say which side is
right or what should be done. A second conflict of the same kind gets the id `C1-2`, `C1-3`, … (the first is `C1`).
"""

from __future__ import annotations

import re
from collections.abc import Sequence
from datetime import date

from app.documents.normalize import find_dates
from app.domain.evidence import Certainty, Fact, FactType
from app.domain.finding import Finding, FindingKind, Severity

C1_FIELD = "7_medications"
C2_FIELD = "14_histology"
VERIFY_ACTION = "create_verification_task"

_PROCEDURE_DATE_LABEL = "datum výkonu"
_ISSUE_DATE_LABEL = "datum vydání"
_DATE = r"(\d{1,2}\.\s*\d{1,2}\.\s*\d{4})"
_LAST_DOSE = re.compile(rf"poslední\s+dávk\w*\s+(?:dne\s+)?{_DATE}", re.IGNORECASE)
_RESUME = re.compile(rf"znovu\s+od\s+{_DATE}", re.IGNORECASE)
_SPECIMEN = re.compile(rf"\bodběr:?\s+(?:dne\s+)?{_DATE}", re.IGNORECASE)


def detect_findings(facts: Sequence[Fact]) -> list[Finding]:
    """All C1 and C2 findings for already as-of-filtered facts, in doc_id order."""
    ordered = sorted(facts, key=lambda f: f.doc_id)
    return [*_numbered("C1", _drug_pause_vs_procedure(ordered)), *_numbered("C2", _specimen_vs_report(ordered))]


def _numbered(base: str, findings: Sequence[Finding]) -> list[Finding]:
    return [f.model_copy(update={"id": base if i == 0 else f"{base}-{i + 1}"}) for i, f in enumerate(findings)]


def _doc_no(doc_id: str) -> str:
    return doc_id.split("_", 1)[0]


def _quote(fact: Fact) -> str:
    return fact.evidence[0].quote


def _cited(fact: Fact) -> str:
    return f"„{_quote(fact)}“"


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


def _finding(kind_id: str, field: str, message: str, used: Sequence[Fact]) -> Finding:
    return Finding(
        id=kind_id,
        kind=FindingKind.DATE_CONFLICT,
        severity=Severity.HIGH,
        message=message,
        field=field,
        docs=sorted({f.doc_id for f in used}),
        evidence=[f.evidence[0] for f in used],
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


def _specimen_vs_report(facts: Sequence[Fact]) -> list[Finding]:
    found: list[Finding] = []
    for issue in facts:
        issue_date = _anchor_date(issue, _ISSUE_DATE_LABEL)
        if issue_date is None:
            continue
        for sample in (f for f in facts if f.doc_id == issue.doc_id and f is not issue):
            specimen_date = _quoted_date(_SPECIMEN, sample) if sample.certainty is Certainty.STATED else None
            if specimen_date is None or specimen_date <= issue_date:
                continue
            procedures = [f for f in facts if f.doc_id != issue.doc_id and _anchor_date(f, _PROCEDURE_DATE_LABEL)]
            message = f"Nesoulad mezi {_cited(sample)} a {_cited(issue)} (dok. {_doc_no(issue.doc_id)})." + "".join(
                f" Pro srovnání: v dok. {_doc_no(f.doc_id)} uvedeno {_cited(f)}." for f in procedures
            )
            found.append(_finding("C2", C2_FIELD, message, [sample, issue, *procedures]))
    return found
