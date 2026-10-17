"""Field rules of `assemble_handover` on small synthetic facts (fictitious data only)."""

from __future__ import annotations

from datetime import date, datetime
from typing import Any

import pytest

from app.domain.common import Role
from app.domain.document import SourceDocument
from app.domain.evidence import Evidence, Fact
from app.domain.finding import Finding, FindingKind, Severity
from app.domain.handover import Handover, HandoverStatus
from app.domain.patient import Patient, Sex
from app.extraction.handover.assemble import assemble_handover, split_documents
from app.extraction.handover.export import to_markdown
from app.extraction.handover.facts import (
    LOINC_LAB_REPORT,
    LOINC_PATHOLOGY,
    LOINC_PROCEDURE_NOTE,
    LOINC_REFERRAL_NOTE,
    HandoverRules,
    same_stem,
)
from app.extraction.handover.fields import birth_number_info
from app.settings import PRAGUE

AS_OF = datetime(2026, 10, 21, 8, 0, tzinfo=PRAGUE)
CONSULT = "11488-4"


def source(doc_id: str, type_code: str = CONSULT, received: datetime | None = None) -> SourceDocument:
    authored = date.fromisoformat(doc_id.rsplit("_", 1)[1])
    return SourceDocument(
        doc_id=doc_id,
        title=f"Zpráva {doc_id[:2]}",
        type_code=type_code,
        authored_at=authored,
        received_at=received or datetime(authored.year, authored.month, authored.day, 12, 0, tzinfo=PRAGUE),
        custodian="Pracoviště",
    )


REFERRAL = source("07_PL_2026-10-02", LOINC_REFERRAL_NOTE)
LAB = source("10_Lab_2026-10-15", LOINC_LAB_REPORT)
EARLY_LAB = source("02_Lab_2026-09-01", LOINC_LAB_REPORT)
PROCEDURE = source("09_EUS_2026-10-12", LOINC_PROCEDURE_NOTE)
PATHOLOGY = source("11_Histo_2026-10-19", LOINC_PATHOLOGY)
CARDIO = source("01_Kardio_2026-07-20")
GASTRO = source("05_Gastro_2026-09-15")
LATE = source("12_Late_2026-10-26")
DOCS = {d.doc_id: d for d in (REFERRAL, LAB, EARLY_LAB, PROCEDURE, PATHOLOGY, CARDIO, GASTRO, LATE)}

_counter = iter(range(10_000))


def fact(
    doc: SourceDocument,
    type_: str,
    field: int,
    value: dict[str, Any],
    *,
    quote: str = "citace",
    certainty: str = "stated",
    clinical_date: date | None = None,
    precision: str | None = None,
    unit: str | None = None,
) -> Fact:
    n = next(_counter)
    return Fact(
        id=f"f{n:04d}",
        doc_id=doc.doc_id,
        type=type_,
        handover_field=field,
        value=value,
        unit=unit,
        clinical_date=clinical_date,
        clinical_date_precision=precision,
        certainty=certainty,
        evidence=[Evidence(doc_id=doc.doc_id, quote=quote, char_start=n, char_end=n + len(quote))],
    )


def text(t: str) -> dict[str, Any]:
    return {"kind": "text", "text": t}


def coded(code: str, system: str, t: str) -> dict[str, Any]:
    return {"kind": "coded", "code": code, "system": system, "text": t}


def person(**kw: str | None) -> dict[str, Any]:
    base: dict[str, Any] = {"kind": "person", "name": None, "relation": None, "phone": None, "email": None}
    return {**base, "address": None, **kw}


def qty(name: str, number: float, flag: str | None = None) -> dict[str, Any]:
    return {"kind": "quantity", "name": name, "number": number, "text_value": None, "comparator": None,
            "flag": flag, "ref_range": None}  # fmt: skip


def med(drug: str, dose: str | None, schedule: str | None) -> dict[str, Any]:
    return {"kind": "medication", "drug": drug, "dose": dose, "schedule": schedule}


def assemble(facts: list[Fact], **kw: Any) -> Handover:
    return assemble_handover("case-1", AS_OF, facts, DOCS, **kw)


# ---------------------------------------------------------------- as-of


def test_split_documents_reports_reasons() -> None:
    late_received = source("08_CT_2026-10-08", received=datetime(2026, 10, 22, 9, 0, tzinfo=PRAGUE))
    included, excluded = split_documents({**DOCS, late_received.doc_id: late_received}, AS_OF)
    assert LATE.doc_id not in included
    reasons = {e.doc_id: e.reason for e in excluded}
    assert reasons[LATE.doc_id].startswith("vytvořeno v den as_of nebo později")
    assert reasons[late_received.doc_id].startswith("doručeno po as_of")


def test_facts_of_excluded_documents_never_reach_a_field() -> None:
    late_allergy = fact(LATE, "allergy", 8, text("AA: PNC"), quote="AA: PNC")
    h = assemble([late_allergy])
    assert h.fields.allergies.status == HandoverStatus.MISSING
    assert all(LATE.doc_id not in str(f.model_dump()) for f in [h.fields.allergies])
    assert LATE.doc_id not in h.included_documents


# ---------------------------------------------------------------- 1, 2 patient and contacts


def test_birth_number_sex_and_checksum() -> None:
    assert birth_number_info("635722/1013") == (Sex.FEMALE, True)
    assert birth_number_info("630722/1013") == (Sex.MALE, False)
    assert birth_number_info("nonsense") is None


def test_patient_identity_with_code_list_lookups() -> None:
    facts = [
        fact(REFERRAL, "patient_identity", 1, person(name="Alena Procházková")),
        fact(REFERRAL, "patient_identity", 1, {"kind": "date", "label": "Datum narození", "date": "1963-07-22"}),
        fact(REFERRAL, "patient_identity", 1, coded("635722/1013", "other", "RČ 635722/1013")),
        fact(REFERRAL, "insurer", 1, coded("211", "other", "ZP 211")),
    ]
    field = assemble(facts).fields.patient
    assert field.value is not None
    assert (field.value.given, field.value.family, field.value.sex) == ("Alena", "Procházková", Sex.FEMALE)
    assert field.value.age_years == 63
    assert field.value.insurer_name == "Zdravotní pojišťovna ministerstva vnitra ČR"
    assert field.status == HandoverStatus.PARTIAL  # address not stated
    assert field.missing == ["address"]


def test_contacts_use_registered_phone_and_report_missing_email_owner() -> None:
    facts = [
        fact(REFERRAL, "contact", 2, person(phone="+420 777 000 541")),
        fact(REFERRAL, "contact", 2, person(phone="+420 311 000 287")),  # GP office, also without a name
        fact(REFERRAL, "contact", 2, person(name="Petra Horká", relation="dcera", phone="+420 777 000 542")),
    ]
    registry = Patient(
        given="Alena", family="Procházková", sex=Sex.FEMALE, birth_date=date(1963, 7, 22),
        birth_number="635722/1013", phone="+420777000541",
    )  # fmt: skip
    field = assemble(facts, patient=registry).fields.contacts
    assert field.value is not None
    assert field.value.patient_phone == "+420 777 000 541"
    assert field.value.contact_person is not None
    assert field.value.contact_person.relation == "dcera"
    assert field.status == HandoverStatus.PARTIAL
    [item] = field.missing_items
    assert (item.item, item.suggested_owner) == ("patient_email", Role.COORDINATOR)

    ambiguous = assemble(facts).fields.contacts  # no registry: two unnamed numbers -> no guess
    assert ambiguous.value is not None
    assert ambiguous.value.patient_phone is None
    assert ambiguous.note is not None


# ---------------------------------------------------------------- 3 diagnosis, 5 MDT question


def test_diagnosis_partial_without_tnm_and_verified_by_pathology() -> None:
    facts = [
        fact(REFERRAL, "diagnosis", 3, coded("C25.0", "MKN-10", "suspektní tumor hlavy pankreatu"),
             certainty="suspected"),
        fact(PATHOLOGY, "diagnosis", 3, coded("8500/3", "MKN-O", "Duktální adenokarcinom pankreatu")),
    ]  # fmt: skip
    field = assemble(facts).fields.diagnosis
    assert field.value is not None
    assert (field.value.icd10, field.value.icdo3_morphology) == ("C25.0", "8500/3")
    assert field.value.verified_histologically_on == date(2026, 10, 19)
    assert field.status == HandoverStatus.PARTIAL
    assert field.missing_items[0].item == "tnm_clinical_stage"
    assert field.missing_items[0].suggested_owner == Role.KOC_PHYSICIAN
    assert field.note is not None
    assert "suspektní" in field.note


@pytest.mark.parametrize(
    ("request_text", "expected"),
    [
        ("Žádám o převzetí do péče KOC a stanovení dalšího postupu v rámci MDT.", HandoverStatus.NEEDS_CLARIFICATION),
        ("Prosím o stanovení dalšího postupu, zejména zda je tumor resekabilní.", HandoverStatus.COMPLETE),
    ],
)
def test_mdt_question_generic_request_needs_clarification(request_text: str, expected: HandoverStatus) -> None:
    field = assemble([fact(REFERRAL, "referral_request", 5, text(request_text), certainty="planned")]).fields
    assert field.mdt_question.status == expected
    assert field.mdt_question.value == request_text


def test_mdt_question_only_from_referral_notes() -> None:
    other = fact(GASTRO, "referral_request", 5, text("vyloučit pneumonii"), certainty="planned")
    field = assemble([other]).fields.mdt_question
    assert field.status == HandoverStatus.MISSING
    assert field.missing_items[0].suggested_owner == Role.GP


# ---------------------------------------------------------------- 6, 7 comorbidities and medications


def test_comorbidities_union_coded_head_absorbs_text() -> None:
    facts = [
        fact(CARDIO, "comorbidity", 6, coded("I48.0", "MKN-10", "Paroxysmální fibrilace síní")),
        fact(REFERRAL, "comorbidity", 6, text("paroxysmální fibrilace síní od r. 2021 na antikoagulaci")),
        fact(REFERRAL, "comorbidity", 6, text("arteriální hypertenze")),
        fact(REFERRAL, "diagnosis", 6, text("biliární infekci"), certainty="suspected"),  # suspected: not listed
    ]
    rows = assemble(facts).fields.comorbidities.value
    assert rows is not None
    assert [(r.text, r.icd10) for r in rows] == [
        ("Paroxysmální fibrilace síní", "I48.0"),
        ("arteriální hypertenze", None),
    ]
    assert rows[0].detail == "paroxysmální fibrilace síní od r. 2021 na antikoagulaci"


def test_medications_dedupe_latest_complete_and_exclusions() -> None:
    facts = [
        fact(CARDIO, "medication", 7, med("apixaban", "5 mg", "1-0-1")),
        fact(GASTRO, "medication", 7, med("apixaban", None, None)),
        fact(REFERRAL, "medication", 7, med("paracetamol", "500 mg", "při bolesti max. 4× denně")),
        fact(GASTRO, "medication", 7, med("paracetamol", "500 mg", "při bolesti nebo teplotě")),
        fact(GASTRO, "medication", 7, med("ciprofloxacin", "500 mg", "1-0-1 po dobu 7 dní"),
             clinical_date=date(2026, 9, 2)),
        fact(REFERRAL, "medication", 7, med("ciprofloxacinem", None, "7 dní")),
        fact(PROCEDURE, "medication", 7, med("propofol", "180 mg i.v.", "frakcionovaně")),
    ]  # fmt: skip
    field = assemble(facts).fields.medications
    assert field.value is not None
    assert [(m.drug, m.dose, m.schedule) for m in field.value] == [
        ("apixaban", "5 mg", "1-0-1"),
        ("paracetamol", "500 mg", "při bolesti max. 4× denně"),
    ]
    assert field.note is not None
    assert "ciprofloxacin" in field.note


def test_same_stem_tolerates_czech_case_endings() -> None:
    assert same_stem("ciprofloxacinu", "ciprofloxacin")
    assert same_stem("leukocytóza", "Leukocyty")
    assert not same_stem("bisoprolol", "perindopril")


# ---------------------------------------------------------------- 8, 9, 10 allergies, PS, weight


def test_performance_status_is_never_inferred() -> None:
    facts = [fact(REFERRAL, "symptom", 11, text("Soběstačná"), quote="Soběstačná")]
    field = assemble(facts).fields.performance_status
    assert field.status == HandoverStatus.MISSING
    assert field.value is None
    [item] = field.missing_items
    assert (item.item, item.suggested_owner) == ("ecog", Role.KOC_PHYSICIAN)


def test_allergy_verbatim() -> None:
    facts = [fact(REFERRAL, "allergy", 8, text("AA: neguje"), certainty="negated", quote="AA: neguje")]
    field = assemble(facts).fields.allergies
    assert (field.status, field.value) == (HandoverStatus.COMPLETE, "AA: neguje")


@pytest.mark.parametrize(("days", "expected"), [(30, HandoverStatus.COMPLETE), (31, HandoverStatus.STALE)])
def test_weight_stale_boundary(days: int, expected: HandoverStatus) -> None:
    measured = date.fromordinal(AS_OF.date().toordinal() - days)
    facts = [
        fact(CARDIO, "vital_sign", 10, qty("Výška", 165), unit="cm"),
        fact(CARDIO, "vital_sign", 10, qty("hmotnost", 69), unit="kg"),
        fact(GASTRO, "vital_sign", 10, qty("Hmotnost", 65), unit="kg", clinical_date=measured),
    ]
    field = assemble(facts, rules=HandoverRules(stale_vitals_days=30)).fields.weight_height
    assert field.status == expected
    assert field.value is not None
    assert [w.kg for w in field.value.weights] == [69, 65]  # history kept, latest last
    if expected == HandoverStatus.STALE:
        assert field.missing_items[0].suggested_owner == Role.KOC_STAFF
        assert field.note is not None
        assert "demo pravidlo" in field.note


# ---------------------------------------------------------------- 11-15


def test_symptom_onset_is_a_reported_past_date() -> None:
    facts = [
        fact(REFERRAL, "symptom", 11, text("Od poloviny srpna 2026 bolesti v epigastriu"),
             clinical_date=date(2026, 8, 1)),
        fact(LAB, "symptom", 11, text("febrilie")),  # clinical question of a lab/imaging request, not a symptom
        fact(CARDIO, "symptom", 11, text("Zátěž toleruje dobře"), clinical_date=date(2026, 7, 20)),
        fact(REFERRAL, "symptom", 11, text("afebrilní"), certainty="negated"),
    ]  # fmt: skip
    value = assemble(facts).fields.symptoms.value
    assert value is not None
    assert value.onset == "Od poloviny srpna 2026 bolesti v epigastriu"
    assert "afebrilní" in value.items  # negations are self-contained statements, shown verbatim
    assert "febrilie" not in value.items


def test_examinations_one_row_per_non_referral_document() -> None:
    rows = assemble([]).fields.examinations.value
    assert rows is not None
    assert REFERRAL.doc_id not in {r.doc_id for r in rows}
    assert LATE.doc_id not in {r.doc_id for r in rows}
    assert [r.date for r in rows] == sorted(r.date for r in rows)


def test_labs_markers_first_latest_first_restatements_dropped() -> None:
    facts = [
        fact(EARLY_LAB, "lab_result", 13, qty("CRP", 86, "H"), unit="mg/l", clinical_date=date(2026, 9, 1)),
        fact(LAB, "lab_result", 13, qty("CRP", 18, "H"), unit="mg/l", clinical_date=date(2026, 10, 15)),
        fact(LAB, "lab_result", 13, qty("CA 19-9", 312, "H"), unit="kU/l", clinical_date=date(2026, 10, 15)),
        fact(GASTRO, "lab_result", 13, qty("CRP", 86), unit="mg/l"),  # restated in a consult note
    ]
    rows = assemble(facts).fields.labs.value
    assert rows is not None
    assert [(r.test, r.value, r.date) for r in rows] == [
        ("CA 19-9", 312, date(2026, 10, 15)),
        ("CRP", 18, date(2026, 10, 15)),
        ("CRP", 86, date(2026, 9, 1)),
    ]


def test_histology_parsed_from_pathology_facts() -> None:
    facts = [
        fact(PATHOLOGY, "examination", 12, text("Číslo vyšetření: B-2026/15921")),
        fact(PATHOLOGY, "admin_date", 14, {"kind": "date", "label": "Datum vydání", "date": "2026-10-19"}),
        fact(PATHOLOGY, "histology", 14, text("CK7 pozitivní")),
        fact(PATHOLOGY, "histology", 14, text("CDX2 negativní")),
        fact(PATHOLOGY, "histology", 14, text("SMAD4 exprese zachována")),
        fact(PATHOLOGY, "histology", 14, text("perineurální invaze")),
        fact(PATHOLOGY, "histology", 14, text("středně až málo diferencovaný (G2–G3)")),
    ]
    value = assemble(facts).fields.histology.value
    assert value is not None
    assert value.report_id == "B-2026/15921"
    assert value.issued == date(2026, 10, 19)
    assert value.ihc == {"CK7": "+", "CDX2": "-", "SMAD4": "exprese zachována"}
    assert (value.perineural_invasion, value.grade) == (True, "G2–G3")


# ---------------------------------------------------------------- findings (F3-1 plug-in), export


def test_conflict_findings_mark_fields_with_a_value() -> None:
    facts = [fact(CARDIO, "medication", 7, med("apixaban", "5 mg", "1-0-1"))]
    findings = [
        Finding(id="C1", kind=FindingKind.DATE_CONFLICT, severity=Severity.HIGH, message="nesoulad mezi daty",
                field="7_medications"),
        Finding(id="C9", kind=FindingKind.DATE_CONFLICT, severity=Severity.HIGH, message="nesoulad",
                field="9_performance_status"),
        Finding(id="M1", kind=FindingKind.MISSING, severity=Severity.HIGH, message="chybí", field="7_medications"),
    ]  # fmt: skip
    h = assemble(facts, findings=findings)
    assert h.fields.medications.status == HandoverStatus.COMPLETE_WITH_CONFLICT
    assert h.fields.medications.conflicts == ["C1"]
    assert h.fields.performance_status.status == HandoverStatus.MISSING  # nothing to contradict
    assert [f.id for f in h.findings] == ["C1", "C9", "M1"]


def test_markdown_export_has_every_section() -> None:
    md = to_markdown(assemble([fact(REFERRAL, "allergy", 8, text("AA: neguje"), quote="AA: neguje")]))
    for n in range(1, 16):
        assert f"\n## {n}. " in md
    assert "> [07_PL_2026-10-02] „AA: neguje“" in md
    assert "oddíly nepotvrzené lékařem jsou návrh" in md
    assert "## 8. Alergie (AA) — kompletní (návrh, nepotvrzeno)" in md
    assert "Chybí: ecog" in md
    assert "ošetřující lékař KOC" in md


def test_comorbidity_fragment_keeps_its_source_context() -> None:
    facts = [
        fact(CARDIO, "comorbidity", 6, coded("I10", "MKN-10", "Arteriální hypertenze")),
        fact(CARDIO, "comorbidity", 6, text("Hypertenze kompenzovaná.")),
        fact(REFERRAL, "comorbidity", 6, text("myomy"), quote="st. p. hysterektomii pro myomy (2010)"),
    ]
    rows = assemble(facts).fields.comorbidities.value
    assert rows is not None
    assert [(r.text, r.detail) for r in rows] == [
        ("Arteriální hypertenze", "Hypertenze kompenzovaná."),
        ("myomy", "st. p. hysterektomii pro myomy (2010)"),
    ]


def test_medication_points_to_documented_drug_plans() -> None:
    facts = [
        fact(REFERRAL, "medication", 7, med("apixaban", "5 mg", "1-0-1")),
        fact(PROCEDURE, "medication", 7, med("Apixaban", None, "vysazen 48 h před výkonem")),
        fact(CARDIO, "documented_plan", 7, text("Medikace beze změn."), certainty="planned"),
        fact(CARDIO, "documented_plan", 7, text("vysadit apixaban 48 hodin předem"), certainty="planned"),
    ]
    h = assemble(facts)
    assert h.fields.medications.note is not None
    assert h.fields.medications.note.startswith("apixaban: viz dokumentované pokyny")
    assert h.fields.other.value == ["Uvedeno v dokumentaci (Zpráva 01, 20. 7. 2026): vysadit apixaban 48 hodin předem"]


def test_every_value_has_an_item_with_dated_evidence() -> None:
    facts = [
        fact(EARLY_LAB, "lab_result", 13, qty("CRP", 86, "H"), unit="mg/l", clinical_date=date(2026, 9, 1)),
        fact(REFERRAL, "allergy", 8, text("AA: neguje"), quote="AA: neguje"),
    ]
    h = assemble(facts)
    [lab] = h.fields.labs.items
    assert (lab.label, lab.value, lab.unit, lab.clinical_date) == ("CRP", 86, "mg/l", date(2026, 9, 1))
    assert lab.evidence[0].authored_at == date(2026, 9, 1)
    assert lab.evidence[0].received_at == EARLY_LAB.received_at
    assert h.fields.allergies.items[0].evidence[0].quote == "AA: neguje"
    assert h.fields.performance_status.items == []  # missing: no value, no item


# ---------------------------------------------------------------- review regressions (PR #14)


def test_as_of_day_is_the_prague_day_whatever_the_offset() -> None:
    # 2026-10-20T23:30Z is 21. 10. 01:30 in Prague: a report authored on 20. 10. is known at that moment
    doc = source("08_CT_2026-10-20", received=datetime(2026, 10, 20, 12, 0, tzinfo=PRAGUE))
    utc_as_of = datetime.fromisoformat("2026-10-20T23:30:00+00:00")
    included, excluded = split_documents({doc.doc_id: doc}, utc_as_of)
    assert doc.doc_id in included
    assert excluded == []


def test_named_third_party_email_is_not_the_patients() -> None:
    facts = [
        fact(REFERRAL, "contact", 2, person(phone="+420 777 000 541")),
        fact(REFERRAL, "contact", 2, person(name="MUDr. Tomáš Řezníček", email="ordinace@example.cz")),
    ]
    field = assemble(facts).fields.contacts
    assert field.value is not None
    assert field.value.patient_email is None
    assert "patient_email" in field.missing


def test_conflict_on_stale_field_is_recorded_without_hiding_stale() -> None:
    facts = [fact(CARDIO, "vital_sign", 10, qty("hmotnost", 69), unit="kg")]
    finding = Finding(id="C7", kind=FindingKind.DATE_CONFLICT, severity=Severity.HIGH, message="nesoulad",
                      field="10_weight_height")  # fmt: skip
    field = assemble(facts, findings=[finding]).fields.weight_height
    assert field.status == HandoverStatus.STALE
    assert field.conflicts == ["C7"]


def test_every_finding_kind_is_linked_to_its_section_but_only_conflicts_change_status() -> None:
    facts = [fact(CARDIO, "vital_sign", 10, qty("hmotnost", 69), unit="kg")]
    findings = [
        Finding(id="S1", kind=FindingKind.STALE, severity=Severity.MEDIUM, message="zastaralé",
                field="10_weight_height"),
        Finding(id="M1", kind=FindingKind.MISSING, severity=Severity.HIGH, message="chybí",
                field="9_performance_status"),
        Finding(id="Q1", kind=FindingKind.NEEDS_CLARIFICATION, severity=Severity.MEDIUM, message="upřesnit",
                field="5_mdt_question"),
        Finding(id="M3", kind=FindingKind.MISSING, severity=Severity.MEDIUM, message="chybí",
                field="2_contacts.patient_email + referring_physician_email"),
        Finding(id="D1", kind=FindingKind.MISSING_DOCUMENT, severity=Severity.MEDIUM, message="chybí dokument"),
    ]  # fmt: skip
    h = assemble(facts, findings=findings)
    assert (h.fields.weight_height.finding_ids, h.fields.weight_height.conflicts) == (["S1"], [])
    assert h.fields.weight_height.status == HandoverStatus.STALE
    assert h.fields.performance_status.finding_ids == ["M1"]
    assert h.fields.mdt_question.finding_ids == ["Q1"]
    assert h.fields.contacts.finding_ids == ["M3"]
    assert h.fields.contacts.status != HandoverStatus.COMPLETE_WITH_CONFLICT
    # A finding without a section is linked nowhere; `1_` does not catch `10_…`.
    assert h.fields.patient.finding_ids == []
    assert all("D1" not in getattr(h.fields, n).finding_ids for n in type(h.fields).model_fields)


def test_conflict_ids_are_also_in_finding_ids() -> None:
    facts = [fact(CARDIO, "vital_sign", 10, qty("hmotnost", 69), unit="kg")]
    finding = Finding(id="C7", kind=FindingKind.DATE_CONFLICT, severity=Severity.HIGH, message="nesoulad",
                      field="10_weight_height")  # fmt: skip
    field = assemble(facts, findings=[finding]).fields.weight_height
    assert (field.conflicts, field.finding_ids) == (["C7"], ["C7"])


def test_unavailable_documents_are_reported_as_excluded() -> None:
    h = assemble([], unavailable={GASTRO.doc_id: "extrakce dokumentu není k dispozici"})
    assert GASTRO.doc_id not in h.included_documents
    assert {e.doc_id: e.reason for e in h.excluded_documents}[GASTRO.doc_id] == "extrakce dokumentu není k dispozici"
    assert GASTRO.doc_id not in {r.doc_id for r in h.fields.examinations.value or []}


def test_lab_with_empty_name_does_not_crash_and_export_keeps_precision() -> None:
    facts = [
        fact(LAB, "lab_result", 13, qty("", 1234567.5), unit="u"),
        fact(GASTRO, "lab_result", 13, qty("CRP", 1234567.5), unit="u"),
    ]
    md = to_markdown(assemble(facts))
    assert "1234567,5 u" in md


def test_confirmation_is_reopened_when_the_content_changes() -> None:
    from app.domain.handover import ReviewState, SectionReview
    from app.extraction.handover.review import overlay_review

    before = assemble([fact(REFERRAL, "allergy", 8, text("AA: neguje"), quote="AA: neguje")])
    confirmed = SectionReview(state=ReviewState.CONFIRMED, value_hash=before.fields.allergies.value_hash)
    same = overlay_review(before, composition_id="c", status="preliminary", sections={"8_allergies": confirmed},
                          edited_values={})  # fmt: skip
    assert same.fields.allergies.review == confirmed

    after = assemble([fact(REFERRAL, "allergy", 8, text("AA: PNC"), quote="AA: PNC")])
    assert after.fields.allergies.value_hash != before.fields.allergies.value_hash
    reopened = overlay_review(after, composition_id="c", status="preliminary", sections={"8_allergies": confirmed},
                              edited_values={})  # fmt: skip
    assert reopened.fields.allergies.review is not None
    assert reopened.fields.allergies.review.state == ReviewState.DRAFT
    assert reopened.fields.allergies.note is not None
    assert "potvrdit znovu" in reopened.fields.allergies.note
