"""The coordinating Task round-trips every machine-owned field (baton role, postponed flag, flags)."""

from __future__ import annotations

from datetime import datetime

from app.domain.case import Case, CaseState
from app.domain.common import PartyRef, Role
from app.fhir.mappers.case import case_from_fhir, case_task_to_fhir
from app.seed import demo_case
from app.settings import PRAGUE

HOLDER = PartyRef(id="dvorakova-lucie@koc2-nemocnice-lipova", display="Koordinátor KOC 2", role=Role.COORDINATOR)


def _task(case: Case, **kwargs: str | None) -> dict[str, object]:
    return case_task_to_fhir(
        case,
        episode_reference="EpisodeOfCare/1",
        patient_reference="Patient/2",
        requester_reference="PractitionerRole/3",
        owner_reference="PractitionerRole/4",
        **kwargs,
    )


def test_all_workflow_fields_survive_a_round_trip() -> None:
    case = Case(
        id="rakathon-2026-prochazkova",
        patient=demo_case.PATIENT,
        state=CaseState.CEKA_NA_PODKLADY,
        baton_holder=HOLDER,
        baton_role=Role.COORDINATOR,
        odlozeny=True,
        resume_baton_role=Role.COORDINATOR,
        resume_on="2026-10-12",
        mdt_start=datetime(2026, 10, 21, 8, 0, tzinfo=PRAGUE),
        conclusion_confirmed=True,
        delivery_receipt=True,
        opened_at=datetime(2026, 10, 2, 9, 30, tzinfo=PRAGUE),
    )

    task = _task(case)
    restored = case_from_fhir(task, demo_case.PATIENT)

    assert task["status"] == "on-hold"
    assert restored == case


def test_plain_case_adds_no_extensions_and_keeps_based_on_and_reason() -> None:
    case = Case(id="rakathon-2026-x", patient=demo_case.PATIENT, state=CaseState.ODESLANO)

    task = _task(case, based_on_reference="ServiceRequest/9", status_reason="důvod")

    assert "extension" not in task
    assert task["basedOn"] == [{"reference": "ServiceRequest/9"}]
    assert task["statusReason"] == {"text": "důvod"}
    assert task["status"] == "requested"
    assert case_from_fhir(task, demo_case.PATIENT).odlozeny is False
