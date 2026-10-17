"""MDT conclusion + feedback Communication against the local IRIS container (`make test-iris-local`; shared servers are
skipped).

Not run by `make check`. Confirms what the in-memory store cannot: that IRIS accepts the transaction the closed-loop
workflow writes (Composition with attester and logical author, Provenance targeting a `urn:uuid`, Communication), and
that the search used to read the conclusion back (`subject` + `type`) finds it. Cleans up only its own tagged resources
and the AuditEvents that reference them.
"""

from __future__ import annotations

import contextlib
import uuid
from collections.abc import AsyncIterator
from datetime import datetime

import httpx
import pytest

from app.domain.common import PartyRef, Role
from app.fhir.bundles import BundleBuilder
from app.fhir.client import FhirClient
from app.fhir.errors import FhirNotFoundError
from app.fhir.mappers.feedback import SID_MESSAGE_ID, feedback_communication_to_fhir
from app.fhir.mappers.mdt_conclusion import (
    TYPE_MDT_CONCLUSION,
    is_conclusion_of,
    mdt_conclusion_from_fhir,
    mdt_conclusion_provenance,
    mdt_conclusion_to_fhir,
)
from app.fhir.repository import FhirRepository
from app.fhir.systems import CS_COMPOSITION_TYPE, CS_WORKFLOW_ROLE, SID_PRACTITIONER_ROLE, TEST_TAG_CODE
from app.security.actor import SYSTEM_ACTOR
from app.settings import PRAGUE, Settings

pytestmark = pytest.mark.iris

TEXT = "Závěr MDT (integrační test): dle zápisu.\nDruhý řádek, <znaky> & diakritika čřž."


@pytest.fixture
async def live() -> AsyncIterator[tuple[FhirClient, str]]:
    settings = Settings()
    if not settings.iris_password.get_secret_value():
        pytest.skip("IRIS_PASSWORD not set (run with --env-file ../.env)")
    tag_code = f"{TEST_TAG_CODE}-{uuid.uuid4().hex[:8]}"
    async with httpx.AsyncClient(timeout=60) as http:
        client = FhirClient(http, settings.fhir_base_url, settings.iris_user, settings.iris_password)
        yield client, tag_code
        for resource_type in (
            "Provenance",
            "Communication",
            "Composition",
            "EpisodeOfCare",
            "PractitionerRole",
            "Patient",
        ):
            for resource in await client.search_all(
                resource_type, {"_tag": f"https://stafeta.example/fhir/CodeSystem/tag|{tag_code}"}
            ):
                reference = f"{resource_type}/{resource['id']}"
                for event in await client.search_all("AuditEvent", {"entity": reference}):
                    await client.delete("AuditEvent", str(event["id"]))
                with contextlib.suppress(FhirNotFoundError):
                    await client.delete(resource_type, str(resource["id"]))


async def test_conclusion_and_feedback_are_accepted_and_read_back(live: tuple[FhirClient, str]) -> None:
    client, tag_code = live
    repo = FhirRepository(client, SYSTEM_ACTOR, tag_code=tag_code)
    run = uuid.uuid4().hex[:8]
    case_id = f"it-{run}"
    signed_at = datetime(2026, 10, 21, 9, 30, tzinfo=PRAGUE)

    patient = await repo.create(
        {"resourceType": "Patient", "identifier": [{"system": "https://stafeta.example/fhir/sid/it", "value": run}]}
    )
    episode = await repo.create(
        {"resourceType": "EpisodeOfCare", "status": "active", "patient": {"reference": patient.reference}}
    )
    role_code = [{"coding": [{"system": CS_WORKFLOW_ROLE, "code": "koc_physician"}]}]
    physician_role = await repo.create(
        {
            "resourceType": "PractitionerRole",
            "identifier": [{"system": SID_PRACTITIONER_ROLE, "value": f"it-{run}@koc2-nemocnice-lipova"}],
            "code": role_code,
        }
    )
    signer = PartyRef(id=f"it-{run}@koc2-nemocnice-lipova", display="Integration test", role=Role.KOC_PHYSICIAN)

    builder = BundleBuilder()
    composition = builder.post(
        mdt_conclusion_to_fhir(
            case_id,
            TEXT,
            patient_reference=patient.reference,
            episode_reference=episode.reference,
            signer=signer,
            signed_at=signed_at,
        )
    )
    builder.post(mdt_conclusion_provenance(target=composition, signer=signer, recorded=signed_at))
    builder.post(
        feedback_communication_to_fhir(
            case_id,
            patient_reference=patient.reference,
            episode_reference=episode.reference,
            sender=signer,
            sender_reference=physician_role.reference,
            recipient_reference=physician_role.reference,
            sent_at=signed_at,
            message_id=f"<{run}@stafeta.example>",
            body="Dobrý den (integrační test).",
        )
    )
    await repo.transaction(builder.build(), audit_in_bundle=True)

    found = await repo.search(
        "Composition", {"subject": patient.reference, "type": f"{CS_COMPOSITION_TYPE}|{TYPE_MDT_CONCLUSION}"}
    )
    [stored] = [c for c in found if is_conclusion_of(c, case_id)]
    record = mdt_conclusion_from_fhir(stored)
    assert record.text == TEXT
    assert record.signer_id == signer.id
    assert record.signed_at == signed_at

    [provenance] = await repo.search("Provenance", {"target": f"Composition/{stored['id']}"})  # urn:uuid was rewritten
    assert provenance["agent"][0]["who"]["identifier"]["value"] == signer.id
    [communication] = await repo.search("Communication", {"subject": patient.reference})
    assert communication["status"] == "completed"
    assert {i["system"] for i in communication["identifier"]} >= {SID_MESSAGE_ID}
