"""The referral creates everything in ONE transaction Bundle with the right shape (recording repository)."""

from __future__ import annotations

import json
import re
from datetime import date, datetime
from typing import Any

import pytest

from app.documents.ingest import UploadedDocument, normalize_upload
from app.domain.case import CaseState
from app.domain.common import PartyRef, Role
from app.domain.errors import ConflictError, ForbiddenError, InvalidInputError
from app.domain.events import TransitionError
from app.domain.patient import Address, ContactPerson, Sex
from app.domain.referral import ReferralSubmission
from app.fhir.referrals import ReferralWriter
from app.seed import demo_case
from app.settings import PRAGUE
from tests.directory_fixtures import demo_directory
from tests.document_fixtures import DOCS_DIR

NOW = datetime(2026, 10, 2, 9, 30, tzinfo=PRAGUE)
DIRECTORY = demo_directory()
GP = DIRECTORY.role(demo_case.GP_ROLE)
assert GP


class FakeRepo:
    def __init__(self, *, existing: dict[str, dict[str, Any]] | None = None, open_episodes: int = 0) -> None:
        self.existing = existing or {}
        self.open_episodes = open_episodes
        self.bundles: list[dict[str, Any]] = []

    async def find_by_identifier(self, resource_type: str, system: str, value: str) -> dict[str, Any] | None:
        return self.existing.get(resource_type)

    async def count(self, resource_type: str, params: dict[str, str]) -> int:
        return self.open_episodes

    async def transaction(self, bundle: dict[str, Any]) -> dict[str, Any]:
        self.bundles.append(bundle)
        return {}


def submission(**overrides: Any) -> ReferralSubmission:
    values: dict[str, Any] = {
        "given": "Alena",
        "family": "Procházková",
        "sex": Sex.FEMALE,
        "birth_date": date(1963, 7, 22),
        "birth_number": "635722/1013",
        "insurer_code": "211",
        "phone": "+420 777 000 541",
        "address": Address(line="Za Školou 17", postal_code="252 41", city="Dolní Břežany"),
        "contact_person": ContactPerson(name="Petra Horká", relation="dcera", phone="+420 777 000 542"),
        "diagnosis_code": "C25.0",
        "diagnosis_text": "suspektní tumor hlavy pankreatu",
        "koc_id": demo_case.KOC2,
        "consent_confirmed": True,
        "priority": "urgent",
        "consent_statements": ["Souhlasí se sdílením informací s dcerou."],
    }
    return ReferralSubmission(**{**values, **overrides})


@pytest.fixture
def letter() -> UploadedDocument:
    path = DOCS_DIR / "07_PL_zadost_KOC2_2026-10-02.docx"
    return normalize_upload(path.name, path.read_bytes())


async def _submit(
    repo: FakeRepo, letter: UploadedDocument, sub: ReferralSubmission | None = None, actor: PartyRef | None = None
) -> None:
    await ReferralWriter(repo).submit(  # type: ignore[arg-type]
        sub or submission(),
        letter,
        [],
        actor=actor or GP.party(),  # type: ignore[union-attr]
        directory=DIRECTORY,
        now=NOW,
        prefill=None,
    )


def entries(repo: FakeRepo) -> dict[str, list[dict[str, Any]]]:
    [bundle] = repo.bundles
    result: dict[str, list[dict[str, Any]]] = {}
    for entry in bundle["entry"]:
        result.setdefault(entry["resource"]["resourceType"], []).append(entry["resource"])
    return result


async def test_one_transaction_creates_the_whole_case(letter: UploadedDocument) -> None:
    repo = FakeRepo()

    await _submit(repo, letter)

    created = entries(repo)
    assert set(created) == {
        "Patient", "RelatedPerson", "Coverage", "EpisodeOfCare", "DocumentReference", "ServiceRequest",
        "Task", "Consent", "Provenance", "AuditEvent",
    }  # fmt: skip
    task = created["Task"][0]
    assert task["businessStatus"]["coding"][0]["code"] == "odeslano"
    assert task["owner"]["display"] == "Koordinátor KOC 2"
    assert task["owner"]["identifier"]["value"] == demo_case.COORDINATOR_ROLE
    assert task["status"] == "requested"
    assert created["ServiceRequest"][0]["priority"] == "urgent"
    assert created["ServiceRequest"][0]["reasonCode"][0]["coding"][0]["code"] == "C25.0"
    assert created["EpisodeOfCare"][0]["managingOrganization"]["reference"].startswith("Organization/")


async def test_references_inside_the_bundle_resolve_to_earlier_entries(letter: UploadedDocument) -> None:
    repo = FakeRepo()
    await _submit(repo, letter)

    [bundle] = repo.bundles
    seen: set[str] = set()
    for entry in bundle["entry"]:
        refs = set(re.findall(r"urn:uuid:[0-9a-f-]{36}", json.dumps(entry["resource"])))
        assert refs <= seen, f"{entry['resource']['resourceType']} references an entry that comes later"
        seen.add(entry["fullUrl"])


async def test_existing_patient_is_reused_not_overwritten(letter: UploadedDocument) -> None:
    repo = FakeRepo(existing={"Patient": {"id": "77"}})

    await _submit(repo, letter)

    created = entries(repo)
    assert "Patient" not in created
    assert created["EpisodeOfCare"][0]["patient"]["reference"] == "Patient/77"


async def test_open_case_of_the_patient_is_a_conflict(letter: UploadedDocument) -> None:
    repo = FakeRepo(existing={"Patient": {"id": "77"}}, open_episodes=1)

    with pytest.raises(ConflictError):
        await _submit(repo, letter)

    assert repo.bundles == []


async def test_provenance_records_the_gp_and_the_letter_not_values(letter: UploadedDocument) -> None:
    repo = FakeRepo()
    await _submit(repo, letter)

    provenance = entries(repo)["Provenance"][0]
    assert provenance["agent"][0]["who"]["identifier"]["value"] == demo_case.GP_ROLE
    assert provenance["entity"][0]["what"]["reference"].startswith("urn:uuid:")
    assert {t["reference"][:4] for t in provenance["target"]} <= {"urn:"}
    assert "Alena" not in str(provenance)


async def test_consent_must_be_confirmed(letter: UploadedDocument) -> None:
    repo = FakeRepo()

    with pytest.raises(TransitionError) as caught:
        await _submit(repo, letter, submission(consent_confirmed=False))

    assert caught.value.code == "guard_failed"
    assert repo.bundles == []


async def test_only_a_gp_may_refer(letter: UploadedDocument) -> None:
    coordinator = DIRECTORY.role(demo_case.COORDINATOR_ROLE)
    assert coordinator

    with pytest.raises(ForbiddenError):
        await _submit(FakeRepo(), letter, actor=coordinator.party())


async def test_unknown_koc_and_koc_without_coordinator_are_rejected(letter: UploadedDocument) -> None:
    with pytest.raises(InvalidInputError):
        await _submit(FakeRepo(), letter, submission(koc_id="neexistuje"))
    with pytest.raises(InvalidInputError, match="koc_without_coordinator"):
        await _submit(FakeRepo(), letter, submission(koc_id=demo_case.KOC1))


async def test_case_id_follows_the_seed_pattern_and_state_is_odeslano(letter: UploadedDocument) -> None:
    repo = FakeRepo()
    await _submit(repo, letter)

    task = entries(repo)["Task"][0]
    assert task["identifier"][0]["value"] == "rakathon-2026-prochazkova"
    assert CaseState.ODESLANO.value in str(task["businessStatus"])
    assert Role.GP.value not in str(task["owner"])


async def test_priority_and_consent_statements_are_what_the_gp_confirmed(letter: UploadedDocument) -> None:
    repo = FakeRepo()
    await _submit(repo, letter, submission(priority="routine", consent_statements=[]))

    created = entries(repo)
    assert created["ServiceRequest"][0]["priority"] == "routine"
    assert "extension" not in created["Consent"][0]


async def test_a_consent_statement_not_in_the_letter_is_rejected(letter: UploadedDocument) -> None:
    with pytest.raises(InvalidInputError):
        await _submit(FakeRepo(), letter, submission(consent_statements=["Souhlasí se vším."]))


async def test_confirmed_statement_is_stored_verbatim(letter: UploadedDocument) -> None:
    repo = FakeRepo()
    await _submit(repo, letter)

    [extension] = entries(repo)["Consent"][0]["extension"]
    assert extension["valueString"] == "Souhlasí se sdílením informací s dcerou."


async def test_duplicate_open_case_message_is_neutral(letter: UploadedDocument) -> None:
    repo = FakeRepo(existing={"Patient": {"id": "77"}}, open_episodes=1)

    with pytest.raises(ConflictError) as caught:
        await _submit(repo, letter)

    message = str(caught.value)
    assert message == "Pro tohoto pacienta již existuje otevřený případ v tomto KOC. Kontaktujte koordinátora."
    assert "rakathon" not in message
