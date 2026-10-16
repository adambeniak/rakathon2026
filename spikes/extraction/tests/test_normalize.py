from __future__ import annotations

import unicodedata
from datetime import date

from documents import (
    doc_from_text,
    find_dates,
    find_month_years,
    match_key,
    normalize_text,
    parse_czech_date,
)


def test_nfc_composes_decomposed_input() -> None:
    decomposed = unicodedata.normalize("NFD", "Procházková")
    assert decomposed != "Procházková"
    assert normalize_text(decomposed) == "Procházková"


def test_nfc_keeps_sub_and_superscripts() -> None:
    assert normalize_text("CHA₂DS₂-VASc, 10⁹/l") == "CHA₂DS₂-VASc, 10⁹/l"


def test_dashes_unified_but_hyphen_untouched() -> None:
    assert normalize_text("C25.0 — tumor -- hlava ‒ x") == "C25.0 – tumor – hlava – x"
    assert normalize_text("apixaban 5 mg 1-0-1, CA 19-9, B-2026/15921") == "apixaban 5 mg 1-0-1, CA 19-9, B-2026/15921"
    assert normalize_text("non‑breaking") == "non-breaking"


def test_whitespace_collapse_and_nbsp() -> None:
    assert normalize_text("  TK 132/80\tmmHg   TF  68/min ") == "TK 132/80 mmHg TF 68/min"
    assert normalize_text("a\n\n  b  \n") == "a\nb"


def test_match_key_maps_back_to_offsets() -> None:
    text = "první řádek\ndruhý   řádek"
    k = match_key(normalize_text(text))
    assert k.key == "první řádek druhý řádek"
    start = k.key.index("řádek druhý")
    s, e = k.span(start, len("řádek druhý"))
    assert normalize_text(text)[s:e] == "řádek\ndruhý"


def test_fold_key_maps_nfkc() -> None:
    k = match_key("CHA₂DS₂ µmol", fold=True)
    assert k.key == "CHA2DS2 μmol"
    s, e = k.span(0, 7)
    assert "CHA₂DS₂ µmol"[s:e] == "CHA₂DS₂"


def test_body_order_and_table_rows(doc) -> None:  # type: ignore[no-untyped-def]
    d = doc("02_")
    kinds = [b.kind for b in d.blocks]
    assert "tr" in kinds and kinds[0] == "p"
    texts = [b.text for b in d.blocks]
    i_hema = texts.index("HEMATOLOGIE – KREVNÍ OBRAZ")
    assert texts[i_hema + 1] == "Vyšetření | Výsledek | Jednotky | Ref. meze"
    assert texts[i_hema + 2] == "Leukocyty | 12,8 H | 10⁹/l | 4,0–10,0"
    assert "Bilirubin celkový | 38 H | µmol/l | 2–17" in texts
    # biochemistry table comes after its heading, urine after biochemistry
    assert (
        texts.index("KLINICKÁ BIOCHEMIE – SÉRUM")
        < texts.index("CRP | 86 H | mg/l | 0–5")
        < texts.index("MOČ – CHEMICKY")
    )
    row = next(b for b in d.blocks if b.text.startswith("CRP"))
    assert row.table_header == "Vyšetření | Výsledek | Jednotky | Ref. meze"
    assert d.text[row.start : row.end] == row.text


def test_empty_trailing_cells_dropped(doc) -> None:  # type: ignore[no-untyped-def]
    texts = [b.text for b in doc("02_").blocks]
    assert "Ampicilin | R" in texts


def test_blocks_offsets_consistent(docs) -> None:  # type: ignore[no-untyped-def]
    for d in docs.values():
        for b in d.blocks:
            assert d.text[b.start : b.end] == b.text


def test_doc_id_and_file_date(docs) -> None:  # type: ignore[no-untyped-def]
    assert len(docs) == 13
    d = docs["09_Biopsie_vykon_KOC2_2026-10-12"]
    assert d.doc_id == "09_Biopsie_vykon_KOC2_2026-10-12"
    assert d.authored_date == date(2026, 10, 12)


def test_header_dates(doc) -> None:  # type: ignore[no-untyped-def]
    assert doc("11_").header_dates["Datum vydání:"] == [date(2026, 10, 19)]
    assert date(2026, 10, 20) not in doc("11_").all_header_dates()  # "odběr 20. 10." is not a header date
    assert doc("02_").header_dates["Vydáno:"] == [date(2026, 9, 4), date(2026, 9, 1)]
    assert doc("02_").header_dates["Odběr:"] == [date(2026, 9, 1)]
    assert doc("09_").header_dates["Datum výkonu:"] == [date(2026, 10, 12)]
    assert doc("03_").header_dates["Datum vyšetření:"] == [date(2026, 9, 3)]
    assert doc("07_").header_dates["V … dne"] == [date(2026, 10, 2)]
    assert date(1963, 7, 22) not in doc("07_").all_header_dates()  # birth date is not a header date
    assert all(not d.warnings for d in [doc("01_"), doc("07_"), doc("11_")])


def test_czech_dates() -> None:
    assert parse_czech_date("20. 7. 2026") == date(2026, 7, 20)
    assert parse_czech_date("4.11.2026 10:30") == date(2026, 11, 4)
    assert parse_czech_date("RTG hrudníku 3. 9. bez změn", year_hint=2026) == date(2026, 9, 3)
    assert parse_czech_date("3. 9. bez změn") is None
    assert parse_czech_date("od poloviny srpna") is None
    assert find_dates("32. 13. 2026") == []
    assert find_month_years("Od poloviny srpna 2026 bolesti") == {(2026, 8)}
    assert find_month_years("Kontrola za 6 měsíců (leden 2027)") == {(2027, 1)}
    assert find_month_years("v červenci 2026") == {(2026, 7)}


def test_doc_from_text() -> None:
    d = doc_from_text("x", "řádek 1\n\nřádek 2", date(2026, 1, 1))
    assert d.text == "řádek 1\nřádek 2" and len(d.blocks) == 2
