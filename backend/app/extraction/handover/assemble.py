"""`assemble_handover`: deterministic assembly of the 15-field handover for a case at an as-of timestamp.

Pure function (no I/O). Inputs are the evidence-locked facts, the documents' metadata (authored, received, type,
custodian), optionally their deterministically parsed header lines (`headers.parse_header`), the registered
patient and the consistency findings (F3-1). The epicrisis is produced by `epicrisis.generate_epicrisis` (one LLM
call) and passed in; without it the deterministic fallback is used.
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping, Sequence
from datetime import datetime

from app.consistency.date_conflicts import RELATED_FIELDS
from app.domain.document import SourceDocument
from app.domain.evidence import Fact
from app.domain.finding import Finding, FindingKind
from app.domain.handover import (
    EpicrisisField,
    ExcludedDocument,
    Handover,
    HandoverFieldBase,
    HandoverFields,
    HandoverStatus,
)
from app.domain.patient import Patient
from app.extraction.handover import fields as f
from app.extraction.handover.epicrisis import fallback_epicrisis
from app.extraction.handover.facts import Context, HandoverRules
from app.extraction.handover.headers import DocumentHeader
from app.extraction.handover.review import value_hash
from app.extraction.lock import AsOfExclusion, as_of_exclusion

# Finding kinds that contradict a stated value (-> complete_with_conflict); missing/stale kinds do not.
CONFLICT_KINDS = frozenset({FindingKind.DATE_CONFLICT, FindingKind.METADATA_MISMATCH, FindingKind.LOST_INFORMATION})
_CONFLICT_ELIGIBLE = frozenset({HandoverStatus.COMPLETE, HandoverStatus.PARTIAL})

_REASONS: dict[AsOfExclusion, str] = {
    "authored_unknown": "datum vytvoření neznámé",
    "authored_after_as_of": "vytvořeno v den as_of nebo později ({as_of})",
    "received_unknown": "čas doručení neznámý",
    "received_after_as_of": "doručeno po as_of ({as_of})",
}


def split_documents(
    documents: Mapping[str, SourceDocument], as_of: datetime
) -> tuple[dict[str, SourceDocument], list[ExcludedDocument]]:
    """AGENTS rule 4: a document counts only if authored <= as_of AND received <= as_of."""
    included: dict[str, SourceDocument] = {}
    excluded: list[ExcludedDocument] = []
    for doc_id in sorted(documents):
        doc = documents[doc_id]
        reason = as_of_exclusion(doc.authored_at, doc.received_at, as_of)
        if reason is None:
            included[doc_id] = doc
        else:
            text = _REASONS[reason].format(as_of=as_of.isoformat(timespec="minutes"))
            excluded.append(ExcludedDocument(doc_id=doc_id, reason=text))
    return included, excluded


def included_facts(facts: Iterable[Fact], included: Mapping[str, SourceDocument]) -> list[Fact]:
    return [fact for fact in facts if fact.doc_id in included]


def assemble_handover(
    case_id: str,
    as_of: datetime,
    facts: Sequence[Fact],
    documents: Mapping[str, SourceDocument],
    *,
    patient: Patient | None = None,
    findings: Sequence[Finding] = (),
    epicrisis: EpicrisisField | None = None,
    rules: HandoverRules | None = None,
    generated_at: datetime | None = None,
    unavailable: Mapping[str, str] | None = None,
    headers: Mapping[str, DocumentHeader] | None = None,
) -> Handover:
    """`unavailable`: doc_id -> Czech reason for known documents whose content could not be read or extracted;
    they are reported in `excluded_documents` instead of silently missing."""
    rules = rules or HandoverRules()
    included, excluded = split_documents(documents, as_of)
    for doc_id, reason in sorted((unavailable or {}).items()):
        if included.pop(doc_id, None) is not None:
            excluded.append(ExcludedDocument(doc_id=doc_id, reason=reason))
    # Second line of defence: facts from excluded (or unknown) documents never reach a field.
    ctx = Context(
        as_of=as_of,
        facts=tuple(included_facts(facts, included)),
        docs=included,
        rules=rules,
        headers={k: h for k, h in (headers or {}).items() if k in included},
    )
    medications = f.medications_field(ctx)
    built = HandoverFields(
        patient=f.patient_field(ctx),
        contacts=f.contacts_field(ctx, patient),
        diagnosis=f.diagnosis_field(ctx),
        epicrisis=epicrisis or fallback_epicrisis(ctx.facts, included),
        mdt_question=f.mdt_question_field(ctx),
        comorbidities=f.comorbidities_field(ctx),
        medications=medications,
        allergies=f.allergies_field(ctx),
        performance_status=f.performance_status_field(ctx),
        weight_height=f.weight_height_field(ctx),
        symptoms=f.symptoms_field(ctx),
        examinations=f.examinations_field(ctx),
        labs=f.labs_field(ctx),
        histology=f.histology_field(ctx),
        other=f.other_field(ctx, medications.value or ()),
    )
    return Handover(
        case_id=case_id,
        as_of=as_of,
        generated_at=generated_at,
        included_documents=sorted(included),
        excluded_documents=excluded,
        fields=with_value_hashes(apply_findings(built, findings)),
        findings=list(findings),
        rules=rules.describe(),
    )


def with_value_hashes(built: HandoverFields) -> HandoverFields:
    updates = {name: getattr(built, name) for name in HandoverFields.model_fields}
    return built.model_copy(
        update={name: field.model_copy(update={"value_hash": value_hash(field)}) for name, field in updates.items()}
    )


def apply_findings(built: HandoverFields, findings: Sequence[Finding]) -> HandoverFields:
    """Mark fields whose value a conflict finding contradicts (`Finding.field` = '7_medications' or '7_…')."""
    updates: dict[str, HandoverFieldBase] = {}
    for name, info in HandoverFields.model_fields.items():
        key = info.alias or name
        prefix = key.split("_", 1)[0] + "_"
        ids = [x.id for x in findings if x.kind in CONFLICT_KINDS and x.field and x.field.startswith(prefix)]
        current: HandoverFieldBase = getattr(built, name)
        related = [x.id for x in findings if x.id not in ids and _shows_anchor(key, current, x)]
        if not ids and not related:
            continue
        # The ids are always recorded; the status changes only where a value exists that the finding contradicts
        # (a stale or needs_clarification status says more than "conflict" and is kept). A related field only
        # shows the same quoted date (field 3 shows the C2 issue date): the id is recorded, its status is kept.
        update: dict[str, object] = {"conflicts": sorted({*current.conflicts, *ids, *related})}
        if ids and current.status in _CONFLICT_ELIGIBLE:
            update["status"] = HandoverStatus.COMPLETE_WITH_CONFLICT
        updates[name] = current.model_copy(update=update)
    return built.model_copy(update=updates) if updates else built


def _shows_anchor(key: str, field: HandoverFieldBase, finding: Finding) -> bool:
    """`key` is a related field of the finding's field (`RELATED_FIELDS`) and cites one of the finding's quotes."""
    if finding.kind not in CONFLICT_KINDS or not finding.field:
        return False
    if key not in RELATED_FIELDS.get(finding.field.split(".", 1)[0], ()):
        return False
    quotes = {(e.doc_id, e.quote) for e in finding.evidence}
    return any((e.doc_id, e.quote) in quotes for e in field.evidence)
