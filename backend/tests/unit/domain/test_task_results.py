"""A received result report completes its pathway step (#132): matching rules and the machine walk."""

from __future__ import annotations

from datetime import date, datetime

import pytest

from app.domain import clock
from app.domain.common import Role
from app.domain.document import SourceDocument
from app.domain.events import TransitionError
from app.domain.task import Task, TaskBusinessStatus, TaskStatus
from app.domain.task_results import RESULT_TYPE_BY_STEP_CODE, deliver_result, matching_result, result_type
from tests.unit.domain.conftest import load_template

T, B = TaskStatus, TaskBusinessStatus
PATHOLOGY, IMAGING = "11526-1", "18748-4"
SCHEDULED = datetime(2026, 10, 12, 13, 0, tzinfo=clock.TZ)
NOW = datetime(2026, 10, 21, 9, 0, tzinfo=clock.TZ)


def histology(status: TaskStatus = T.ACCEPTED, business: TaskBusinessStatus = B.POTVRZENO, **kw: object) -> Task:
    base: dict[str, object] = {
        "id": "c1.histology",
        "case_id": "c1",
        "code": "histology",
        "title": "Histologie",
        "owner_role": Role.EXTERNAL_WORKPLACE,
        "scheduled_at": SCHEDULED,
        "depends_on": ["c1.eus-fnb"],
    }
    return Task.model_validate({**base, **kw, "status": status, "business_status": business})


def report(
    doc_id: str = "11_Histologie_KOC2_2026-10-19",
    type_code: str | None = PATHOLOGY,
    authored: date = date(2026, 10, 19),
    received: datetime = datetime(2026, 10, 19, 16, 0, tzinfo=clock.TZ),
) -> SourceDocument:
    return SourceDocument(doc_id=doc_id, title=doc_id, type_code=type_code, authored_at=authored, received_at=received)


def test_every_mapped_code_is_a_step_of_the_demo_template() -> None:
    codes = {step.code for step in load_template().steps}
    assert set(RESULT_TYPE_BY_STEP_CODE) <= codes
    assert {"algesiology", "psychooncology", "mdt"}.isdisjoint(RESULT_TYPE_BY_STEP_CODE)


@pytest.mark.parametrize(
    ("status", "business", "expected"),
    [
        (T.REQUESTED, B.OBJEDNANO, None),  # not ordered yet
        (T.REQUESTED, B.POTVRZENO, None),  # confirmed but not accepted: a human accepts the order first
        (T.ACCEPTED, B.POTVRZENO, PATHOLOGY),
        (T.IN_PROGRESS, B.POTVRZENO, PATHOLOGY),
        (T.IN_PROGRESS, B.PROVEDENO, PATHOLOGY),
        (T.COMPLETED, B.VYSLEDEK_DORUCEN, None),
        (T.FAILED, B.POTVRZENO, None),
        (T.CANCELLED, B.POTVRZENO, None),
    ],
)
def test_only_an_accepted_or_running_step_waits_for_its_report(
    status: TaskStatus, business: TaskBusinessStatus, expected: str | None
) -> None:
    assert result_type(histology(status, business)) == expected


def test_a_step_without_a_result_report_never_waits() -> None:
    assert result_type(histology(code="algesiology")) is None
    assert result_type(histology(code="ad-hoc")) is None


def test_the_report_must_be_received_by_now_of_the_right_type_and_not_older_than_the_confirmed_date() -> None:
    task = histology()
    good = report()

    assert matching_result(task, [good], NOW) == good
    # the demo clock stands before the upload (16. 10.): the report is not there yet
    assert matching_result(task, [good], datetime(2026, 10, 16, 9, 0, tzinfo=clock.TZ)) is None
    assert matching_result(task, [report(type_code=IMAGING)], NOW) is None
    assert matching_result(task, [report(type_code=None)], NOW) is None
    # authored before the examination date: an older report of the same type is not this result
    assert matching_result(task, [report(authored=date(2026, 10, 11))], NOW) is None
    assert matching_result(task, [report(authored=date(2026, 10, 12))], NOW) is not None


def test_an_older_imaging_report_does_not_complete_the_ct() -> None:
    ct = histology(code="ct-thorax-abdomen", id="c1.ct", scheduled_at=datetime(2026, 10, 8, 8, 0, tzinfo=clock.TZ))
    uz = report("06_UZ_bricha_2026-09-29", IMAGING, date(2026, 9, 29), datetime(2026, 10, 2, 9, 0, tzinfo=clock.TZ))
    ct_report = report(
        "08_CT_KOC1_2026-10-08", IMAGING, date(2026, 10, 8), datetime(2026, 10, 8, 15, 30, tzinfo=clock.TZ)
    )

    assert matching_result(ct, [uz], NOW) is None
    assert matching_result(ct, [uz, ct_report], NOW) == ct_report


def test_the_earliest_received_matching_report_wins() -> None:
    late = report("11b", received=datetime(2026, 10, 20, 9, 0, tzinfo=clock.TZ))
    early = report("11a")

    assert matching_result(histology(), [late, early], NOW) == early


@pytest.mark.parametrize(
    ("status", "business", "events"),
    [
        (T.ACCEPTED, B.POTVRZENO, ["start", "performed", "result_delivered"]),
        (T.IN_PROGRESS, B.POTVRZENO, ["performed", "result_delivered"]),
        (T.IN_PROGRESS, B.PROVEDENO, ["result_delivered"]),
    ],
)
def test_the_step_walks_the_machine_to_result_delivered(
    status: TaskStatus, business: TaskBusinessStatus, events: list[str]
) -> None:
    task, applied = deliver_result(histology(status, business), "11_Histologie_KOC2_2026-10-19", ["c1.eus-fnb"], NOW)

    assert applied == events
    assert (task.status, task.business_status) == (T.COMPLETED, B.VYSLEDEK_DORUCEN)
    assert task.result_doc_id == "11_Histologie_KOC2_2026-10-19"
    assert task.owner is None  # the system records the result; it does not become the owner


def test_the_machine_still_refuses_a_step_whose_predecessor_is_open() -> None:
    with pytest.raises(TransitionError) as exc:
        deliver_result(histology(), "11_Histologie_KOC2_2026-10-19", [], NOW)

    assert exc.value.code == "guard_failed"
