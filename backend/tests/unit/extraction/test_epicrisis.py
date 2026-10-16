"""Epicrisis: post-check, one regeneration, fallback (fake LLM client, no network)."""

from __future__ import annotations

import asyncio
import json
from datetime import date

from app.domain.evidence import Fact
from app.domain.handover import HandoverStatus
from app.extraction.handover.epicrisis import check_sentences, generate_epicrisis, select_facts
from app.extraction.llm import CacheMissError
from tests.unit.extraction.test_handover_assembly import DOCS, GASTRO, LAB, PATHOLOGY, REFERRAL, fact, qty, text

FACTS: list[Fact] = [
    fact(REFERRAL, "symptom", 11, text("bolesti v epigastriu"), quote="bolesti v epigastriu",
         clinical_date=date(2026, 8, 1), precision="month"),
    fact(GASTRO, "diagnosis", 3, text("Cholestatický syndrom"), quote="Cholestatický syndrom"),
    fact(GASTRO, "diagnosis", 3, text("tumor pankreatu"), certainty="suspected",
         quote="Diferenciálně diagnosticky choledocholitiáza, stenóza žlučových cest, tumor pankreatu"),
    fact(PATHOLOGY, "histology", 14, text("perineurální invaze"), quote="s perineurální invazí"),
    fact(LAB, "lab_result", 13, qty("CA 19-9", 312, "H"), unit="kU/l", quote="CA 19-9 | 312 | kU/l"),
    fact(LAB, "lab_result", 13, qty("CRP", 18, "H"), unit="mg/l", quote="CRP | 18 | mg/l"),  # not a tumour marker
]  # fmt: skip


class FakeClient:
    def __init__(self, *responses: str | Exception) -> None:
        self.responses = list(responses)
        self.users: list[str] = []

    async def complete_json(self, *, system: str, user: str, schema: dict[str, object], doc_id: str) -> str:
        self.users.append(user)
        item = self.responses.pop(0)
        if isinstance(item, Exception):
            raise item
        return item


def answer(*sentences: tuple[str, list[str]]) -> str:
    return json.dumps({"sentences": [{"text": t, "fact_ids": ids} for t, ids in sentences]}, ensure_ascii=False)


GOOD = answer(
    ("Od 1. 8. 2026 uvedeny bolesti v epigastriu [F1].", ["F1"]),
    ("CA 19-9 312 kU/l, histologicky perineurální invaze [F4, F5].", ["F4", "F5"]),
)


def test_selection_keeps_tumour_markers_only() -> None:
    aliased = select_facts(FACTS, DOCS)
    assert [a.alias for a in aliased] == ["F1", "F2", "F3", "F4", "F5"]
    assert all("CRP" not in str(a.fact.value) for a in aliased)


def test_valid_answer_maps_aliases_to_fact_ids() -> None:
    field = asyncio.run(generate_epicrisis(FACTS, DOCS, FakeClient(GOOD), case_id="case-1"))
    assert field.status == HandoverStatus.GENERATED_WITH_CITATIONS
    assert field.value is not None
    assert field.value.mode == "llm"
    assert field.value.label == "Návrh AI – čeká na potvrzení lékařem"
    by_alias = {a.alias: a.fact.id for a in select_facts(FACTS, DOCS)}
    assert field.value.sentences[1].fact_ids == [by_alias["F4"], by_alias["F5"]]
    assert field.value.sentences[1].aliases == ["F4", "F5"]
    # one item per sentence; evidence parallel to the aliases, with the source documents' dates
    item = field.items[1]
    assert [ev.quote for ev in item.evidence] == ["CA 19-9 | 312 | kU/l", "s perineurální invazí"]
    assert item.evidence[0].authored_at == date(2026, 10, 15)
    assert {e.quote for e in field.evidence} >= {"bolesti v epigastriu", "CA 19-9 | 312 | kU/l"}


def test_post_check_rejects_uncited_unknown_and_unsupported_numbers() -> None:
    aliased = select_facts(FACTS, DOCS)
    bad = json.loads(
        answer(
            ("Pacientka má bolesti.", ["F1"]),  # no citation in the text
            ("CA 19-9 je 999 kU/l [F5].", ["F5"]),  # number not in the cited fact
            ("Něco dalšího [F9].", ["F9"]),  # unknown alias
        )
    )
    _, problems = check_sentences(bad, aliased)
    assert any("nekončí citací" in p for p in problems)
    assert any("999" in p for p in problems)
    assert any("neexistující" in p for p in problems)


def test_regenerates_once_with_a_different_message() -> None:
    client = FakeClient(answer(("Bez citace.", ["F1"])), GOOD)
    field = asyncio.run(generate_epicrisis(FACTS, DOCS, client, case_id="case-1"))
    assert field.value is not None
    assert field.value.mode == "llm"
    assert len(client.users) == 2
    assert client.users[0] != client.users[1]  # new cache key for the retry


def test_falls_back_after_two_failed_checks() -> None:
    bad = answer(("Bez citace.", ["F1"]))
    field = asyncio.run(generate_epicrisis(FACTS, DOCS, FakeClient(bad, bad), case_id="case-1"))
    assert field.value is not None
    assert field.value.mode == "fallback"
    assert all(s.text.endswith("]") and s.fact_ids for s in field.value.sentences)


def test_cache_miss_falls_back_with_citations() -> None:
    field = asyncio.run(generate_epicrisis(FACTS, DOCS, FakeClient(CacheMissError("miss")), case_id="case-1"))
    assert field.status == HandoverStatus.GENERATED_WITH_CITATIONS
    assert field.value is not None
    assert field.value.mode == "fallback"
    assert field.note is not None
    assert "odpověď AI není uložena" in field.note  # Czech, no internal exception names in UI text
    assert len(field.value.sentences) == 5


def test_post_check_rejects_judgement_and_hidden_suspicion() -> None:
    aliased = select_facts(FACTS, DOCS)
    bad = json.loads(
        answer(
            ("Nález svědčí pro pokročilé onemocnění [F2].", ["F2"]),  # judgement not in the quote
            ("Gastroenterolog uvádí tumor pankreatu [F3].", ["F3"]),  # suspected fact stated as fact
        )
    )
    _, problems = check_sentences(bad, aliased)
    assert any("hodnocení" in p for p in problems)
    assert any("suspektní" in p for p in problems)
    ok = json.loads(answer(("Diferenciálně diagnosticky uveden i tumor pankreatu [F3].", ["F3"])))
    assert check_sentences(ok, aliased)[1] == []


def test_fallback_shows_certainty_and_date_precision() -> None:
    field = asyncio.run(generate_epicrisis(FACTS, DOCS, FakeClient(CacheMissError("miss")), case_id="case-1"))
    assert field.value is not None
    texts = [s.text for s in field.value.sentences]
    assert texts[0] == "8/2026: bolesti v epigastriu [F1]"  # month precision, never an invented day
    assert "15. 9. 2026: suspektní: tumor pankreatu [F3]" in texts


def test_legend_evidence_stays_parallel_when_facts_share_a_quote() -> None:
    line = "apixaban 5 mg 1-0-1, bisoprolol 5 mg 1-0-0"
    shared = [
        fact(REFERRAL, "diagnosis", 3, text("apixaban 5 mg 1-0-1"), quote=line),
        fact(REFERRAL, "diagnosis", 3, text("bisoprolol 5 mg 1-0-0"), quote=line),
    ]
    shared[1] = shared[1].model_copy(update={"evidence": shared[0].evidence})  # identical span
    client = FakeClient(answer(("V dokumentaci uvedeno: apixaban 5 mg 1-0-1, bisoprolol 5 mg 1-0-0 [F1, F2].",
                                ["F1", "F2"])))  # fmt: skip
    field = asyncio.run(generate_epicrisis(shared, DOCS, client, case_id="case-1"))
    assert field.value is not None
    assert field.value.mode == "llm"
    assert field.value.sentences[0].aliases == ["F1", "F2"]
    assert len(field.items[0].evidence) == 2  # one entry per alias, even with the same quote
