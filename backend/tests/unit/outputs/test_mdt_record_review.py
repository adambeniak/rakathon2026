"""Findings of the clinical-safety and security reviews of the MDT record export, one test each."""

from __future__ import annotations

import io
import zipfile

import pytest
from docx import Document

from app.domain.handover import Handover, ReviewState, SectionReview
from app.outputs.mdt_record import (
    LABEL_CONFIRMED,
    LABEL_PARTIAL,
    TEMPLATE,
    MdtRecordError,
    _verify_complete,
    is_draft,
)
from tests.unit.outputs.test_mdt_record import CONFIRMED_AT, PHYSICIAN, _confirmed, _lines, _text, render


def _with(handover: Handover, name: str, **changes: object) -> Handover:
    field = getattr(handover.fields, name)
    patched = field.model_copy(update=changes)
    return handover.model_copy(update={"fields": handover.fields.model_copy(update={name: patched})})


def test_notes_and_missing_items_are_printed_under_the_section_label(story_handover: Handover) -> None:
    text = _text(render(story_handover))

    assert "Chybí: TNM klinické stadium – v dokumentaci neuvedeno" in text
    assert "Kód MKN-10 je v dokumentu 07_PL_zadost_KOC2_2026-10-02 uveden jako suspektní." in text
    assert "Kontakty: Chybí: e-mail pacienta" in text
    assert "Váha a výška: Chybí: aktuální hmotnost" in text
    assert "Váha a výška: neaktuální údaj" in text
    assert "explicit_mdt_question" not in text  # internal keys never reach the document
    assert "Chybí: ecog " not in text


def test_diagnosis_and_comorbidities_name_their_source_documents(story_handover: Handover) -> None:
    text = _text(render(story_handover))

    assert "Duktální adenokarcinom pankreatu [07_PL_zadost_KOC2_2026-10-02, 11_Histologie_KOC2_2026-10-19]" in text
    assert "Morfologie (ICD-O-3): 8500/3" in text
    assert "Histologicky ověřeno: 19. 10. 2026" in text
    assert "C25.0 [07_PL_zadost_KOC2_2026-10-02, 11_Histologie_KOC2_2026-10-19]" in text
    assert "Zdroj: [01_Kardiologie_2026-07-20" in text


def test_a_confirmation_shows_who_and_when(story_handover: Handover) -> None:
    text = _text(render(_confirmed(story_handover)))

    assert f"{LABEL_CONFIRMED} (MUDr. Lenka Marková, 20. 10. 2026 15:00)" in text
    assert is_draft(story_handover)
    assert not is_draft(_confirmed(story_handover))


def test_a_partly_confirmed_section_names_what_is_not_confirmed(story_handover: Handover) -> None:
    review = SectionReview(
        state=ReviewState.CONFIRMED, by=PHYSICIAN, at=CONFIRMED_AT, value_hash=story_handover.fields.patient.value_hash
    )
    handover = _with(story_handover, "patient", review=review)

    text = _text(render(handover))

    assert f"{LABEL_PARTIAL} (MUDr. Lenka Marková, 20. 10. 2026 15:00) – nepotvrzeno: Kontakty, Váha a výška" in text


def test_the_draft_status_is_on_every_page(story_handover: Handover) -> None:
    def header(data: bytes) -> str:
        return Document(io.BytesIO(data)).sections[0].header.paragraphs[0].text

    assert header(render(story_handover)) == "NÁVRH – obsahuje oddíly nepotvrzené lékařem"
    assert header(render(_confirmed(story_handover))) == ""


def test_dimensionless_units_and_month_only_onsets_do_not_mislead(story_handover: Handover) -> None:
    text = _text(render(story_handover))

    assert "Hematokrit 0,37 1" not in text  # reads as 0,371
    assert "Hematokrit 0,37;" in text
    onset_lines = [line for line in text.splitlines() if "Od poloviny srpna 2026" in line]
    assert onset_lines
    assert not any("(1. 8. 2026)" in line for line in onset_lines)  # documented only to the month


def test_exclusions_read_as_prose_and_the_footer_carries_the_export_time(story_handover: Handover) -> None:
    text = _text(render(story_handover))

    assert "2026-10-21T" not in text
    assert "– po MDT (vytvořeno v den začátku MDT nebo později; začátek MDT 21. 10. 2026 08:00)" in text
    assert "dne 21. 10. 2026 07:30." in text  # the export time, not the cut-off


def test_the_fallback_epicrisis_has_one_cited_line_per_fact(story_handover: Handover) -> None:
    text = _text(render(story_handover))

    assert "Souhrn AI nebyl vytvořen; níže je přehled citovaných údajů z dokumentace." in text
    assert "– 20. 7. 2026: Zátěž toleruje dobře (2 patra bez zastavení). [F1] [01_Kardiologie_2026-07-20]" in text


def test_hostile_characters_neither_truncate_nor_reshape_the_document(story_handover: Handover) -> None:
    diagnosis = story_handover.fields.diagnosis
    assert diagnosis.value is not None
    hostile = diagnosis.value.model_copy(update={"text": "A\ud800B\x07C\x0cD\x00E\x1bF\nG"})
    baseline = _lines(render(story_handover))

    lines = _lines(render(_with(story_handover, "diagnosis", value=hostile)))

    assert any(line.startswith("Název diagnózy | AB C D") for line in lines)  # lone surrogate and control chars gone
    assert any(line.startswith("Zápis vygeneroval") for line in lines)  # the last paragraph is still there
    assert len(lines) == len(baseline)  # no extra paragraphs, no page break, no lost tables


def test_a_birth_number_in_free_text_is_redacted(story_handover: Handover) -> None:
    handover = _with(story_handover, "other", note="Pacientka 635722/1013 souhlasí.")

    text = _text(render(handover))

    assert "635722" not in text
    assert "Pacientka [RČ vynecháno] souhlasí." in text


def test_an_incomplete_document_is_an_error_not_a_download(story_handover: Handover) -> None:
    with pytest.raises(MdtRecordError):
        _verify_complete(render(story_handover), "tato věta v dokumentu není")


def test_the_template_and_the_export_carry_no_foreign_metadata(story_handover: Handover) -> None:
    for blob in (render(story_handover), TEMPLATE.read_bytes()):
        with zipfile.ZipFile(io.BytesIO(blob)) as package:
            names = package.namelist()
            core = package.read("docProps/core.xml").decode("utf-8")
            everything = "".join(package.read(n).decode("utf-8", "ignore") for n in names)
        assert "docProps/custom.xml" not in names
        assert "MSIP" not in everything
        assert "Bielčiková" not in core
        assert "<dc:creator>Štafeta</dc:creator>" in core
