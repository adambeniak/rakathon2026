"""C1/C2 date-conflict rules: positive and negative cases on hand-built facts (no LLM, no cache)."""

from __future__ import annotations

from app.consistency import detect_findings
from app.domain.evidence import Certainty, Evidence, Fact, FactType
from app.domain.finding import Finding, FindingKind

DOC09 = "09_Biopsie_vykon_KOC2_2026-10-12"
DOC11 = "11_Histologie_KOC2_2026-10-19"
PROCEDURE_QUOTE = "Datum výkonu: 12. 10. 2026"
DOSE_QUOTE = "Apixaban vysazen 48 h před výkonem (poslední dávka 18. 10. 2026 večer)."
RESUME_QUOTE = "Při nekomplikovaném průběhu apixaban znovu od 21. 10. 2026 ráno."
SPECIMEN_QUOTE = "Materiál: ložisko hlavy pankreatu, EUS-FNB 22G (odběr 20. 10. 2026)"
ISSUE_QUOTE = "Datum vydání: 19. 10. 2026"
_ids = iter(range(1, 10_000))


def fact(doc_id: str, type_: FactType, value: dict[str, str | None], quote: str, field: int = 12) -> Fact:
    return Fact(
        id=f"F{next(_ids)}",
        doc_id=doc_id,
        type=type_,
        handover_field=field,
        value=value,
        certainty=Certainty.STATED,
        evidence=[Evidence(doc_id=doc_id, quote=quote)],
    )


def admin_date(doc_id: str, label: str, iso: str, quote: str) -> Fact:
    return fact(doc_id, FactType.ADMIN_DATE, {"kind": "date", "label": label, "date": iso}, quote)


def procedure(iso: str = "2026-10-12", quote: str = PROCEDURE_QUOTE) -> Fact:
    return admin_date(DOC09, "Datum výkonu", iso, quote)


def dose(quote: str = DOSE_QUOTE) -> Fact:
    return fact(DOC09, FactType.MEDICATION, {"kind": "medication", "drug": "Apixaban"}, quote, field=7)


def resume(quote: str = RESUME_QUOTE) -> Fact:
    return fact(DOC09, FactType.DOCUMENTED_PLAN, {"kind": "text", "text": "apixaban znovu"}, quote, field=7)


def specimen(quote: str = SPECIMEN_QUOTE) -> Fact:
    return fact(DOC11, FactType.PROCEDURE, {"kind": "text", "text": "ložisko hlavy pankreatu"}, quote)


def issue(iso: str = "2026-10-19", quote: str = ISSUE_QUOTE) -> Fact:
    return admin_date(DOC11, "Datum vydání", iso, quote)


def only(findings: list[Finding], id_: str) -> Finding:
    (found,) = [x for x in findings if x.id == id_]
    return found


def mentions(message: str, *parts: str) -> bool:
    return all(part in message for part in parts)


def quotes(finding: Finding) -> list[str]:
    return [e.quote for e in finding.evidence]


# --- C1: drug pause vs procedure date -------------------------------------------------------------------------


def test_c1_last_dose_after_procedure_is_flagged_with_all_quotes() -> None:
    c1 = only(detect_findings([procedure(), dose(), resume()]), "C1")
    assert c1.kind is FindingKind.DATE_CONFLICT
    assert c1.field == "7_medications"
    assert c1.docs == [DOC09]
    assert quotes(c1) == [PROCEDURE_QUOTE, DOSE_QUOTE, RESUME_QUOTE]
    assert mentions(c1.message, "12. 10. 2026", "18. 10. 2026", "21. 10. 2026", "dok. 09")
    assert c1.message.startswith("Nesoulad mezi")
    # quoted, not paraphrased: the condition of the restart survives
    assert f"„{RESUME_QUOTE}“" in c1.message
    assert "Při nekomplikovaném průběhu" in c1.message


def test_c1_without_resume_quote_still_flags() -> None:
    c1 = only(detect_findings([procedure(), dose()]), "C1")
    assert quotes(c1) == [PROCEDURE_QUOTE, DOSE_QUOTE]
    assert "V téže dokumentaci" not in c1.message


def test_c1_restart_quote_must_name_the_same_drug() -> None:
    other_drug = resume("Při nekomplikovaném průběhu metformin znovu od 21. 10. 2026 ráno.")
    c1 = only(detect_findings([procedure(), dose(), other_drug]), "C1")
    assert quotes(c1) == [PROCEDURE_QUOTE, DOSE_QUOTE]
    assert "V téže dokumentaci" not in c1.message


def test_c1_last_dose_before_procedure_is_consistent() -> None:
    ok = dose("Apixaban vysazen 48 h před výkonem (poslední dávka 10. 10. 2026 večer).")
    assert detect_findings([procedure(), ok, resume()]) == []


def test_c1_last_dose_on_procedure_day_is_not_flagged() -> None:
    same = dose("Apixaban (poslední dávka 12. 10. 2026 ráno).")
    assert detect_findings([procedure(), same]) == []


def test_c1_needs_a_procedure_date_in_the_same_document() -> None:
    assert detect_findings([dose(), resume()]) == []
    other_doc = admin_date("08_CT_KOC1_2026-10-08", "Datum výkonu", "2026-10-08", "Datum výkonu: 8. 10. 2026")
    assert detect_findings([other_doc, dose()]) == []


def test_c1_ignores_dates_without_a_year() -> None:
    assert detect_findings([procedure(), dose("Apixaban (poslední dávka 18. 10. večer).")]) == []
    # a year-less date must not hand over to the next dated mention
    assert detect_findings([procedure(), dose("(poslední dávka 10. 10. večer, kontrola INR 25. 10. 2026)")]) == []


def test_only_stated_facts_trigger_a_rule() -> None:
    for certainty in (Certainty.NEGATED, Certainty.PLANNED, Certainty.SUSPECTED):
        assert detect_findings([procedure(), dose().model_copy(update={"certainty": certainty})]) == []
        assert detect_findings([procedure().model_copy(update={"certainty": certainty}), dose()]) == []
        assert detect_findings([specimen().model_copy(update={"certainty": certainty}), issue()]) == []
        assert detect_findings([specimen(), issue().model_copy(update={"certainty": certainty})]) == []


def test_anchor_date_is_read_from_the_quote_not_from_the_model_label() -> None:
    mislabelled = admin_date(DOC09, "Datum výkonu", "2026-10-12", "V Praze dne 12. 10. 2026")
    assert detect_findings([mislabelled, dose()]) == []
    wrong_iso = admin_date(DOC09, "Datum výkonu", "2026-10-30", PROCEDURE_QUOTE)  # quote says 12. 10. 2026
    c1 = only(detect_findings([wrong_iso, dose()]), "C1")
    assert quotes(c1)[0] == PROCEDURE_QUOTE


# --- C2: specimen date vs report date -------------------------------------------------------------------------


def test_c2_specimen_after_report_issue_date_is_flagged_with_all_quotes() -> None:
    c2 = only(detect_findings([specimen(), issue(), procedure()]), "C2")
    assert c2.kind is FindingKind.DATE_CONFLICT
    assert c2.field == "14_histology"
    assert c2.docs == [DOC09, DOC11]
    assert quotes(c2) == [SPECIMEN_QUOTE, ISSUE_QUOTE, PROCEDURE_QUOTE]
    assert mentions(c2.message, "20. 10. 2026", "19. 10. 2026", "12. 10. 2026", "dok. 11", "dok. 09")
    assert c2.message.startswith("Nesoulad mezi")


def test_c2_without_procedure_date_elsewhere_still_flags() -> None:
    c2 = only(detect_findings([specimen(), issue()]), "C2")
    assert c2.docs == [DOC11]
    assert quotes(c2) == [SPECIMEN_QUOTE, ISSUE_QUOTE]


def test_c2_specimen_on_or_before_report_date_is_consistent() -> None:
    before = specimen("Materiál: ložisko hlavy pankreatu, EUS-FNB 22G (odběr 12. 10. 2026)")
    assert detect_findings([before, issue(), procedure()]) == []
    same_day = specimen("Materiál: EUS-FNB 22G (odběr 19. 10. 2026)")
    assert detect_findings([same_day, issue()]) == []


def test_c2_procedure_date_equal_to_specimen_date_is_still_shown_for_comparison() -> None:
    same = procedure("2026-10-20", "Datum výkonu: 20. 10. 2026")
    c2 = only(detect_findings([specimen(), issue(), same]), "C2")
    assert "Datum výkonu: 20. 10. 2026" in quotes(c2)
    assert "Pro srovnání" in c2.message


def test_dates_must_directly_follow_the_cue_phrase() -> None:
    later = specimen("Materiál: EUS-FNB 22G (odběr proveden, kontrola 25. 10. 2026)")
    assert detect_findings([later, issue()]) == []
    later_dose = dose("Apixaban vysazen (poslední dávka podána večer, kontrola 25. 10. 2026)")
    assert detect_findings([procedure(), later_dose]) == []


def test_c2_needs_report_issue_date_and_year_in_same_document() -> None:
    assert detect_findings([specimen()]) == []
    assert detect_findings([specimen("Materiál: EUS-FNB 22G (odběr 20. 10.)"), issue()]) == []
    # only the specimen collection counts, not other words that start with "odběr"
    assert detect_findings([specimen("Odběrové místo Praha, přijato 22. 10. 2026"), issue()]) == []
    assert detect_findings([specimen("laboratorní odběry 22. 10. 2026"), issue()]) == []
    elsewhere = admin_date(DOC09, "Datum vydání", "2026-10-19", ISSUE_QUOTE)
    assert detect_findings([specimen(), elsewhere]) == []


# --- both rules -----------------------------------------------------------------------------------------------


def test_second_conflict_of_the_same_kind_gets_its_own_id() -> None:
    other = "10_Jina_zprava_2026-10-14"
    second = admin_date(other, "Datum výkonu", "2026-10-14", "Datum výkonu: 14. 10. 2026")
    drug = {"kind": "medication", "drug": "Warfarin"}
    later_dose = fact(other, FactType.MEDICATION, drug, "Warfarin (poslední dávka 16. 10. 2026)", field=7)
    ids = [x.id for x in detect_findings([procedure(), dose(), second, later_dose])]
    assert ids == ["C1", "C1-2"]


def test_both_rules_independent_and_stable_ids() -> None:
    facts = [specimen(), issue(), procedure(), dose(), resume()]
    assert [x.id for x in detect_findings(facts)] == ["C1", "C2"]
    assert [x.id for x in detect_findings(list(reversed(facts)))] == ["C1", "C2"]


def test_wording_is_neutral_no_advice() -> None:
    for finding in detect_findings([specimen(), issue(), procedure(), dose(), resume()]):
        text = finding.message.casefold()
        assert not any(
            w in text for w in ("doporuč", "měl", "mělo", "má být", "nutno", "vysadit", "podat", "dávk" + "ovat")
        )
        assert finding.suggested_action == "flag_and_create_verification_task"


def test_czech_date_text_is_parsed_not_compared_as_strings() -> None:
    # "9. 10." sorts after "18. 10." as text; the rule must compare real dates.
    early = dose("Apixaban (poslední dávka 9. 10. 2026 večer).")
    assert detect_findings([procedure(), early]) == []
