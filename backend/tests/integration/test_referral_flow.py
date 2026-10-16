"""Demo steps 1–2 against a live IRIS (`uv run --env-file ../.env pytest -m iris tests/integration`).

Needs the seeded directory (`make seed` or `make demo-reset`). NOT run by the agents that wrote it (no IRIS available
to them): the first human run also answers the open questions of ADR-0005 (If-Match and urn:uuid in transactions).
Everything this run writes carries its own tag and is deleted afterwards, AuditEvents of the run included.
"""

from __future__ import annotations

import contextlib
import uuid
from collections.abc import AsyncIterator
from datetime import date, datetime
from typing import Any

import httpx
import pytest

from app.documents.ingest import normalize_upload
from app.domain.case import CaseState
from app.domain.common import Role
from app.domain.patient import ContactPerson, Sex
from app.domain.referral import ReferralSubmission
from app.fhir.cases import CaseReader
from app.fhir.client import FhirClient
from app.fhir.directory import Directory, DirectoryReader
from app.fhir.referrals import ReferralWriter
from app.fhir.repository import FhirRepository
from app.fhir.systems import CS_TAG, TEST_TAG_CODE
from app.fhir.workflow import RequestItem, RequestWorkflow
from app.seed import demo_case
from app.seed.loader import RESET_ORDER
from app.settings import Settings
from tests.document_fixtures import DOCS_DIR

pytestmark = pytest.mark.iris


@pytest.fixture
async def live() -> AsyncIterator[tuple[FhirClient, str]]:
    settings = Settings()
    if not settings.iris_password.get_secret_value():
        pytest.skip("IRIS_PASSWORD not set (run with --env-file ../.env)")
    tag_code = f"{TEST_TAG_CODE}-{uuid.uuid4().hex[:8]}"
    async with httpx.AsyncClient(timeout=60) as http:
        client = FhirClient(http, settings.fhir_base_url, settings.iris_user, settings.iris_password)
        try:
            yield client, tag_code
        finally:
            for resource_type in (*RESET_ORDER, "AuditEvent"):
                for found in await client.search_all(resource_type, {"_tag": f"{CS_TAG}|{tag_code}", "_count": "100"}):
                    with contextlib.suppress(Exception):  # cleanup only; never mask the test result
                        await client.delete(resource_type, str(found["id"]))


async def test_gp_refers_coordinator_accepts_requests_and_receives_reports(live: tuple[FhirClient, str]) -> None:
    client, tag_code = live
    directory: Directory = await DirectoryReader(client).load()
    gp = directory.role(demo_case.GP_ROLE)
    coordinator = directory.role(demo_case.COORDINATOR_ROLE)
    if gp is None or coordinator is None or directory.org(demo_case.KOC2) is None:
        pytest.skip("seeded directory missing (run `make demo-reset`)")
    suffix = uuid.uuid4().hex[:6]
    now = datetime.fromisoformat("2026-10-02T09:30:00+02:00")

    gp_repo = FhirRepository(client, gp.party(), tag_code=tag_code)
    letter_path = DOCS_DIR / "07_PL_zadost_KOC2_2026-10-02.docx"
    letter = normalize_upload(letter_path.name, letter_path.read_bytes())
    submission = ReferralSubmission(
        given="Testovací",
        family=f"Pacient{suffix}",
        sex=Sex.FEMALE,
        birth_date=date(1985, 1, 1),
        birth_number=f"855101{int(suffix, 16) % 10000:04d}",
        diagnosis_code="C25.0",
        diagnosis_text="suspektní tumor hlavy pankreatu",
        koc_id=demo_case.KOC2,
        consent_confirmed=True,
        priority="routine",
        contact_person=ContactPerson(name="Test Kontakt", relation="dcera"),
    )
    result = await ReferralWriter(gp_repo).submit(
        submission, letter, [], actor=gp.party(), directory=directory, now=now, prefill=None
    )

    coordinator_repo = FhirRepository(client, coordinator.party(), tag_code=tag_code)
    reader = CaseReader(coordinator_repo)
    overview = await reader.overview(result.case_id)
    assert overview.case.state is CaseState.ODESLANO
    assert overview.case.baton_holder is not None
    assert overview.case.baton_holder.display == "Koordinátor KOC 2"

    workflow = RequestWorkflow(coordinator_repo, reader)
    accepted = await workflow.transition(
        result.case_id, "accept", actor=coordinator.party(), directory=directory, now=now
    )
    assert accepted.case.state is CaseState.TRIAGE

    requested = await workflow.create_requests(
        result.case_id,
        [RequestItem("RTG plic 3. 9. 2026", "rc-modrany", date(2026, 9, 3))],
        actor=coordinator.party(),
        directory=directory,
        now=now,
    )
    assert requested.case.state is CaseState.CEKA_NA_PODKLADY

    report_path = DOCS_DIR / "03_RTG_plic_2026-09-03.docx"
    received: Any = await workflow.receive_document(
        result.case_id,
        normalize_upload(report_path.name, report_path.read_bytes(), doc_id=f"03_RTG_plic_{suffix}_2026-09-03"),
        authored_at=date(2026, 9, 3),
        request_id=requested.requests[0].task.id,
        actor=coordinator.party(),
        directory=directory,
        now=now,
    )
    assert received.case_event == "podklady_kompletni"
    final = await reader.overview(result.case_id)
    assert final.case.state is CaseState.KOMPLETNI
    assert final.case.baton_holder is not None
    assert final.case.baton_holder.role is Role.KOC_PHYSICIAN
