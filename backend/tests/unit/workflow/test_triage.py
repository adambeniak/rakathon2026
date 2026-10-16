"""Triage on letter 07: the five listed reports with their workplaces; the GP's own epicrisis (04) is not proposed."""

from __future__ import annotations

from datetime import date, datetime

import pytest

from app.documents.normalize import NormalizedDoc
from app.domain.document import SourceDocument
from app.domain.triage import ListedExam, ProposalStatus, propose_requests
from app.extraction.llm import CACHE_MODEL, LLMClient
from app.extraction.pipeline import extract_facts
from app.extraction.referral_exams import listed_exams
from app.seed import demo_case
from app.settings import PRAGUE
from tests.directory_fixtures import demo_directory

DIRECTORY = demo_directory()
ORGS = [o.org for o in DIRECTORY.orgs]
ROLES = [(r.role, r.display) for r in DIRECTORY.roles]


@pytest.fixture
async def exams(docs: dict[str, NormalizedDoc]) -> list[ListedExam]:
    letter = docs["07_PL_zadost_KOC2_2026-10-02"]
    result = await extract_facts(letter, LLMClient(model=CACHE_MODEL, cache_only=True))
    return listed_exams(letter, list(result.accepted))


async def test_only_the_five_listed_reports_are_taken_from_the_letter(exams: list[ListedExam]) -> None:
    assert [e.exam_date for e in exams] == [
        date(2026, 9, 1), date(2026, 9, 3), date(2026, 9, 15), date(2026, 9, 29), date(2026, 7, 20)
    ]  # fmt: skip
    assert all(e.evidence[0].quote[0].isdigit() for e in exams)  # numbered list items, not epicrisis sentences


async def test_proposals_resolve_the_workplace_of_each_report(exams: list[ListedExam]) -> None:
    proposals = propose_requests(exams, [], ORGS, ROLES)

    assert [(p.exam_date, p.recipient_org_id, p.resolved_by) for p in proposals] == [
        (date(2026, 9, 1), "labjih", "organization"),
        (date(2026, 9, 3), "rc-modrany", "organization"),
        (date(2026, 9, 15), "poliklinika-jizni", "organization"),
        (date(2026, 9, 29), "poliklinika-jizni", "organization"),
        (date(2026, 7, 20), "kardio-jesenice", "practitioner"),
    ]
    assert {p.status for p in proposals} == {ProposalStatus.MISSING}
    assert all(p.evidence for p in proposals)
    assert "04" not in "".join(p.key for p in proposals)


async def test_report_already_in_the_case_is_not_proposed_again(exams: list[ListedExam]) -> None:
    lab = SourceDocument(
        doc_id="02_Laborator_2026-09-01",
        title="Laboratoř",
        authored_at=date(2026, 9, 1),
        received_at=datetime(2026, 10, 2, 10, 0, tzinfo=PRAGUE),
        custodian="Laboratoř LabJih s.r.o.",
    )

    proposals = propose_requests(exams, [lab], ORGS, ROLES)

    assert proposals[0].status is ProposalStatus.ATTACHED
    assert proposals[0].attached_doc_id == "02_Laborator_2026-09-01"
    assert [p.status for p in proposals[1:]] == [ProposalStatus.MISSING] * 4


async def test_unknown_workplace_stays_unresolved_for_the_coordinator() -> None:
    odd = ListedExam.model_validate(
        {
            "label": "MR mozku 5. 9. 2026 (Neznámé centrum Brno)",
            "exam_date": date(2026, 9, 5),
            "evidence": [{"doc_id": "x", "quote": "MR mozku"}],
        }
    )

    [proposal] = propose_requests([odd], [], ORGS, ROLES)

    assert proposal.recipient_org_id is None
    assert proposal.resolved_by is None
    assert proposal.status is ProposalStatus.MISSING


def test_the_directory_has_the_workplaces_the_letter_names() -> None:
    assert {o.id for o in ORGS} >= {
        "labjih",
        "rc-modrany",
        "poliklinika-jizni",
        "kardio-jesenice",
        demo_case.GP_PRACTICE,
    }


async def test_same_date_but_other_workplace_is_only_possibly_attached(exams: list[ListedExam]) -> None:
    other = SourceDocument(
        doc_id="CT_2026-09-01",
        title="CT",
        authored_at=date(2026, 9, 1),
        received_at=datetime(2026, 10, 2, 10, 0, tzinfo=PRAGUE),
        custodian="Radiologické centrum Modřany",
    )

    proposals = propose_requests(exams, [other], ORGS, ROLES)

    assert proposals[0].status is ProposalStatus.POSSIBLY_ATTACHED  # the lab report of that day is still not proven
