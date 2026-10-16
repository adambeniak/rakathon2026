"""Write side of the referral: ONE transaction Bundle creates the whole case (owner: P1 adapter, written by P4)."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

from app.documents.ingest import UploadedDocument
from app.documents.normalize import match_key, stem_date
from app.domain import case_machine
from app.domain.case import Case
from app.domain.case_ids import case_id_candidates
from app.domain.common import PartyRef, Role
from app.domain.directory import OrganizationKind
from app.domain.document import SourceDocument
from app.domain.errors import ConflictError, ForbiddenError, InvalidInputError
from app.domain.evidence import Evidence
from app.domain.patient import Patient
from app.domain.referral import ReferralPrefill, ReferralSubmission, compare_with_prefill
from app.fhir.audit import build_domain_audit_event
from app.fhir.bundles import BundleBuilder
from app.fhir.directory import Directory
from app.fhir.mappers.case import case_task_to_fhir, episode_of_care_to_fhir
from app.fhir.mappers.document import document_to_fhir
from app.fhir.mappers.patient import coverage_to_fhir, patient_to_fhir, rc_value, related_person_to_fhir
from app.fhir.mappers.referral import consent_to_fhir, provenance_to_fhir, service_request_to_fhir
from app.fhir.repository import FhirRepository
from app.fhir.systems import CZ_RODNE_CISLO, SID_CASE_TASK, SID_COVERAGE, SID_RELATED_PERSON

LETTER_TYPE_CODE = "57133-1"  # LOINC Referral note
LETTER_TITLE = "Žádost praktického lékaře o převzetí do péče KOC"


@dataclass(frozen=True)
class ReferralResult:
    case_id: str
    warnings: tuple[str, ...]


def enrich_prefill(prefill: ReferralPrefill, directory: Directory) -> ReferralPrefill:
    """Directory lookups that are not extracted text: insurer name, GP match."""
    update: dict[str, object] = {}
    code = prefill.insurer_code.value
    if code and (insurer := directory.insurer(code)):
        update["insurer_name"] = insurer.org.name
    gp_name = prefill.requesting_gp.value
    if gp_name:
        wanted = _plain(gp_name)
        match = next(
            (
                r
                for r in directory.roles
                if r.role.role is Role.GP and (_plain(r.display) == wanted or _plain(r.display) in wanted)
            ),
            None,
        )
        if match:
            update["requesting_gp_role_id"] = match.role.id
    return prefill.model_copy(update=update) if update else prefill


def _plain(name: str) -> str:
    return " ".join(name.lower().replace(",", " ").split())


class ReferralWriter:
    def __init__(self, repository: FhirRepository) -> None:
        self._repo = repository

    async def submit(
        self,
        submission: ReferralSubmission,
        letter: UploadedDocument,
        attachments: list[UploadedDocument],
        *,
        actor: PartyRef,
        directory: Directory,
        now: datetime,
        prefill: ReferralPrefill | None,
    ) -> ReferralResult:
        if actor.role is not Role.GP:
            raise ForbiddenError("only a GP may send a referral")
        gp = directory.role(actor.id)
        koc = directory.org(submission.koc_id)
        if gp is None:
            raise ForbiddenError("the GP is not in the directory")
        if koc is None or koc.org.kind is not OrganizationKind.KOC:
            raise InvalidInputError(f"unknown KOC {submission.koc_id!r}")
        coordinator = directory.role_holder(koc.org.id, Role.COORDINATOR)
        coordinator_entry = directory.role(coordinator.id) if coordinator else None
        if coordinator is None or coordinator_entry is None:
            raise InvalidInputError("the selected KOC has no coordinator in the directory (koc_without_coordinator)")

        haystack = match_key(letter.doc.text).key
        for statement in submission.consent_statements:
            if match_key(statement).key not in haystack:
                raise InvalidInputError("a consent statement does not occur in the letter")
        doc_ids = [letter.doc.doc_id, *(a.doc.doc_id for a in attachments)]
        if len(set(doc_ids)) != len(doc_ids):
            raise InvalidInputError("document names must be unique within the referral")

        patient = Patient(
            given=submission.given,
            family=submission.family,
            sex=submission.sex,
            birth_date=submission.birth_date,
            birth_number=submission.birth_number,
            insurer_code=submission.insurer_code,
            phone=submission.phone,
            address=submission.address,
        )
        existing_patient = await self._repo.find_by_identifier(
            "Patient", CZ_RODNE_CISLO, rc_value(patient.birth_number)
        )
        if existing_patient is not None:
            open_episodes = await self._repo.count(
                "EpisodeOfCare",
                {"patient": f"Patient/{existing_patient['id']}", "organization": koc.ref, "status": "active"},
            )
            if open_episodes:
                raise ConflictError(
                    "Pro tohoto pacienta již existuje otevřený případ v tomto KOC. Kontaktujte koordinátora."
                )
        case_id = await self._free_case_id(now.year, patient.family)

        submitted = case_machine.submit_referral(
            case_id,
            patient,
            actor.role,
            case_machine.CaseContext(
                consent_confirmed=submission.consent_confirmed,
                target_koc=koc.org.id,
                patient_id=rc_value(patient.birth_number),
            ),
            now,
        )
        case: Case = submitted.case.model_copy(update={"baton_holder": coordinator})

        warnings: list[str] = []
        bundle = BundleBuilder()
        created: list[str] = []

        if existing_patient is not None:
            patient_ref = f"Patient/{existing_patient['id']}"
        else:
            patient_ref = bundle.post(patient_to_fhir(patient, general_practitioner=gp.ref))
            created.append(patient_ref)
        related_ref = None
        if submission.contact_person is not None:
            related = related_person_to_fhir(submission.contact_person, patient_reference=patient_ref, patient=patient)
            related_ref = await self._existing_ref(
                "RelatedPerson", SID_RELATED_PERSON, str(related["identifier"][0]["value"])
            )
            if related_ref is None:
                related_ref = bundle.post(related)
                created.append(related_ref)
        if patient.insurer_code:
            insurer = directory.insurer(patient.insurer_code)
            if insurer is None:
                warnings.append("insurer_not_in_directory")
            else:
                coverage = coverage_to_fhir(
                    patient=patient,
                    patient_reference=patient_ref,
                    payor_reference=insurer.ref,
                    payor_display=insurer.org.name,
                )
                if await self._existing_ref("Coverage", SID_COVERAGE, str(coverage["identifier"][0]["value"])) is None:
                    created.append(bundle.post(coverage))

        episode_ref = bundle.post(
            episode_of_care_to_fhir(
                case,
                patient_reference=patient_ref,
                managing_organization_reference=koc.ref,
                care_manager=(coordinator, coordinator_entry.ref),
            )
        )
        created.append(episode_ref)

        letter_ref = bundle.post(
            document_to_fhir(
                SourceDocument(
                    doc_id=letter.doc.doc_id,
                    title=LETTER_TITLE,
                    type_code=LETTER_TYPE_CODE,
                    authored_at=letter.doc.authored_date or now.date(),
                    received_at=now,
                    custodian=_gp_organization(directory, gp.role.organization_id),
                    author=gp.display,
                    file_name=letter.file_name,
                    content_type=letter.content_type,
                ),
                letter.content,
                patient_reference=patient_ref,
                episode_reference=episode_ref,
                custodian_reference=_org_ref(directory, gp.role.organization_id),
                author_reference=gp.ref,
            )
        )
        for extra in attachments:
            bundle.post(
                document_to_fhir(
                    SourceDocument(
                        doc_id=extra.doc.doc_id,
                        title=extra.file_name,
                        authored_at=extra.doc.authored_date or stem_date(extra.doc.doc_id) or now.date(),
                        received_at=now,
                        custodian=_gp_organization(directory, gp.role.organization_id),
                        author=gp.display,
                        file_name=extra.file_name,
                        content_type=extra.content_type,
                    ),
                    extra.content,
                    patient_reference=patient_ref,
                    episode_reference=episode_ref,
                    custodian_reference=_org_ref(directory, gp.role.organization_id),
                    author_reference=gp.ref,
                )
            )

        request_ref = bundle.post(
            service_request_to_fhir(
                case_id,
                submission,
                patient_reference=patient_ref,
                requester=actor,
                requester_reference=gp.ref,
                koc_reference=koc.ref,
                letter_reference=letter_ref,
                authored_on=now,
                diagnosis_evidence=_unedited_diagnosis_evidence(prefill, submission),
            )
        )
        created.append(request_ref)
        task_ref = bundle.post(
            case_task_to_fhir(
                case,
                episode_reference=episode_ref,
                patient_reference=patient_ref,
                requester_reference=gp.ref,
                owner_reference=coordinator_entry.ref,
                based_on_reference=request_ref,
            )
        )
        created.append(task_ref)
        statements = list(submission.consent_statements)
        created.append(
            bundle.post(
                consent_to_fhir(
                    case_id,
                    patient_reference=patient_ref,
                    koc_reference=koc.ref,
                    letter_reference=letter_ref,
                    recorded_at=now,
                    statements=statements,
                )
            )
        )
        edited, added = compare_with_prefill(prefill, submission) if prefill else (None, None)
        bundle.post(
            provenance_to_fhir(
                targets=created,
                letter_reference=letter_ref,
                confirmed_by=actor,
                confirmed_by_reference=gp.ref,
                recorded_at=now,
                edited=edited,
                added=added,
            )
        )
        for event in submitted.events:
            if event.kind.value == "audit":
                bundle.post(build_domain_audit_event(event, actor=actor, entities=[task_ref, episode_ref]))

        await self._repo.transaction(bundle.build())
        return ReferralResult(case_id=case_id, warnings=tuple(warnings))

    async def _free_case_id(self, year: int, family: str) -> str:
        for candidate in case_id_candidates(year, family):
            if await self._repo.find_by_identifier("Task", SID_CASE_TASK, candidate) is None:
                return candidate
        raise AssertionError("unreachable: candidates are infinite")

    async def _existing_ref(self, resource_type: str, system: str, value: str) -> str | None:
        found = await self._repo.find_by_identifier(resource_type, system, value)
        return f"{resource_type}/{found['id']}" if found else None


def _org_ref(directory: Directory, org_id: str) -> str | None:
    entry = directory.org(org_id)
    return entry.ref if entry else None


def _gp_organization(directory: Directory, org_id: str) -> str | None:
    entry = directory.org(org_id)
    return entry.org.name if entry else None


def _unedited_diagnosis_evidence(prefill: ReferralPrefill | None, submission: ReferralSubmission) -> list[Evidence]:
    """The letter's quote backs the stored diagnosis only while the GP did not change it."""
    diagnosis = prefill.suspected_diagnosis if prefill else None
    if diagnosis is None or diagnosis.value is None:
        return []
    if (diagnosis.value.code, diagnosis.value.text) != (submission.diagnosis_code, submission.diagnosis_text):
        return []
    return list(diagnosis.evidence)
