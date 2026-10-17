"""GET /api/cases and /api/cases/{id}: read-backs of the workflow's own records.

`readiness_waivers` (#131): blocking readiness items a KOC physician waived at `mark_ready_mdt` (who, when, why).
`gp_opened_at` (#113): when the referring GP first opened the MDT conclusion (audit-only `gp_opened`); null otherwise.
How they are read from FHIR is tested in tests/unit/fhir/test_cases_reader.py.
"""

from __future__ import annotations

from collections.abc import Iterator
from datetime import datetime

import pytest
from fastapi.testclient import TestClient

from app.api.deps import (
    LlmClients,
    get_case_reader,
    get_fhir_client,
    get_handover_store,
    get_iris_pool,
    get_llm_clients,
)
from app.domain.case import CaseState
from app.domain.pathway import RecordedWaiver
from app.fhir.cases import CaseDetailView, CaseExtras, CaseOverview
from app.main import create_app
from app.settings import PRAGUE, Settings
from tests.unit.api.fake_handover_store import FakeStore
from tests.unit.api.test_api import CASE, DOCUMENT, FakeFhir, FakeLlm, FakePool, FakeReader

OPENED_AT = datetime(2026, 10, 22, 9, 15, 30, tzinfo=PRAGUE)
WAIVED_AT = datetime(2026, 10, 21, 7, 45, tzinfo=PRAGUE)
WAIVER = RecordedWaiver(
    item="performance_status",
    reason="PS doplní lékař osobně na MDT.",
    by_id="markova-lenka@koc2-nemocnice-lipova",
    by_display="MUDr. Lenka Marková",
    at=WAIVED_AT,
)
SENT = CASE.model_copy(update={"state": CaseState.ZPETNA_VAZBA_ODESLANA})


class ReadBackReader(FakeReader):
    """A case past the feedback: the GP opened the conclusion and one readiness item was waived."""

    async def list_cases(self) -> list[CaseOverview]:
        return [CaseOverview(case=SENT, document_count=13, extras=CaseExtras(gp_opened_at=OPENED_AT))]

    async def get_case(self, case_id: str) -> CaseDetailView:
        return CaseDetailView(
            case=SENT,
            documents=[DOCUMENT],
            extras=CaseExtras(gp_opened_at=OPENED_AT),
            readiness_waivers=(WAIVER,),
        )


def _client(settings: Settings, reader: FakeReader) -> Iterator[TestClient]:
    app = create_app(settings)
    app.dependency_overrides[get_case_reader] = lambda: reader
    app.dependency_overrides[get_fhir_client] = lambda: FakeFhir()
    app.dependency_overrides[get_iris_pool] = lambda: FakePool()
    llm = LlmClients(FakeLlm('{"facts": []}'), FakeLlm(None))
    app.dependency_overrides[get_llm_clients] = lambda: llm
    store = FakeStore()
    app.dependency_overrides[get_handover_store] = lambda: store
    with TestClient(app) as client:
        yield client


@pytest.fixture
def client(settings: Settings) -> Iterator[TestClient]:
    yield from _client(settings, ReadBackReader())


@pytest.fixture
def plain_client(settings: Settings) -> Iterator[TestClient]:
    yield from _client(settings, FakeReader())


def test_case_detail_shows_who_waived_which_readiness_item_when_and_why(client: TestClient) -> None:
    body = client.get("/api/cases/rakathon-2026-prochazkova").json()

    assert body["readiness_waivers"] == [
        {
            "item": "performance_status",
            "reason": "PS doplní lékař osobně na MDT.",
            "waived_by": "MUDr. Lenka Marková",
            "waived_at": "2026-10-21T07:45:00+02:00",
        }
    ]
    assert body["gp_opened_at"] == "2026-10-22T09:15:30+02:00"


def test_case_list_carries_gp_opened_at_but_no_waivers(client: TestClient) -> None:
    [case] = client.get("/api/cases").json()

    assert case["gp_opened_at"] == "2026-10-22T09:15:30+02:00"
    assert "readiness_waivers" not in case  # detail only


def test_without_records_the_fields_are_empty_and_null(plain_client: TestClient) -> None:
    detail = plain_client.get("/api/cases/rakathon-2026-prochazkova").json()
    [summary] = plain_client.get("/api/cases").json()

    assert detail["readiness_waivers"] == []
    assert detail["gp_opened_at"] is None  # unknown, never a guessed "not opened"
    assert summary["gp_opened_at"] is None
