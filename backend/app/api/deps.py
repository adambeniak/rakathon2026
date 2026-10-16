"""FastAPI dependencies: settings, shared clients and adapters (created per request, cheap)."""

from __future__ import annotations

from typing import Annotated

from fastapi import Depends, Request

from app.api.clients import DirectoryProviderDep as DirectoryProviderDep  # re-exports: routes and tests import these
from app.api.clients import FhirClientDep as FhirClientDep
from app.api.clients import SettingsDep as SettingsDep
from app.api.clients import get_directory_provider as get_directory_provider
from app.api.clients import get_fhir_client as get_fhir_client
from app.api.clients import get_http as get_http
from app.api.clients import get_settings as get_settings
from app.domain.common import PartyRef
from app.extraction.handover.epicrisis import EPICRISIS_PROMPT_VERSION
from app.extraction.llm import LLMClient
from app.extraction.pipeline import CompletionClient
from app.fhir.cases import CaseReader
from app.fhir.handover_store import HandoverStore
from app.fhir.referrals import ReferralWriter
from app.fhir.repository import FhirRepository
from app.fhir.systems import DEMO_TAG_CODE
from app.fhir.triage import TriageReader
from app.fhir.workflow import CaseWorkflow, RequestWorkflow
from app.iris.db import IrisPool
from app.security.actor import current_actor


def get_iris_pool(request: Request) -> IrisPool:
    pool: IrisPool = request.app.state.iris_pool
    return pool


IrisPoolDep = Annotated[IrisPool, Depends(get_iris_pool)]
ActorDep = Annotated[PartyRef, Depends(current_actor)]


def get_repository(client: FhirClientDep, actor: ActorDep, settings: SettingsDep) -> FhirRepository:
    return FhirRepository(client, actor, tag_code=DEMO_TAG_CODE if settings.stafeta_demo_mode else None)


RepositoryDep = Annotated[FhirRepository, Depends(get_repository)]


def get_case_reader(repository: RepositoryDep) -> CaseReader:
    return CaseReader(repository)


CaseReaderDep = Annotated[CaseReader, Depends(get_case_reader)]


def get_case_workflow(repository: RepositoryDep, reader: CaseReaderDep) -> CaseWorkflow:
    return CaseWorkflow(repository, reader)


CaseWorkflowDep = Annotated[CaseWorkflow, Depends(get_case_workflow)]


def get_llm_client(settings: SettingsDep) -> LLMClient:
    return LLMClient.from_settings(settings)


LlmClientDep = Annotated[LLMClient, Depends(get_llm_client)]


def get_referral_writer(repository: RepositoryDep) -> ReferralWriter:
    return ReferralWriter(repository)


ReferralWriterDep = Annotated[ReferralWriter, Depends(get_referral_writer)]


def get_request_workflow(repository: RepositoryDep, reader: CaseReaderDep) -> RequestWorkflow:
    return RequestWorkflow(repository, reader)


RequestWorkflowDep = Annotated[RequestWorkflow, Depends(get_request_workflow)]


def get_triage_reader(repository: RepositoryDep, reader: CaseReaderDep, llm: LlmClientDep) -> TriageReader:
    return TriageReader(repository, reader, llm)


TriageReaderDep = Annotated[TriageReader, Depends(get_triage_reader)]


def get_handover_store(repository: RepositoryDep) -> HandoverStore:
    return HandoverStore(repository)


HandoverStoreDep = Annotated[HandoverStore, Depends(get_handover_store)]


class LlmClients:
    """The extraction and epicrisis clients (separate prompt versions = separate cache keys)."""

    def __init__(self, extraction: CompletionClient, epicrisis: CompletionClient) -> None:
        self.extraction = extraction
        self.epicrisis = epicrisis


def get_llm_clients(request: Request, settings: SettingsDep) -> LlmClients:
    """Created on first use (not at startup: live mode needs APIM settings) and shared, so the clients'
    concurrency limits apply across requests."""
    clients: LlmClients | None = getattr(request.app.state, "llm_clients", None)
    if clients is None:
        clients = LlmClients(
            LLMClient.from_settings(settings),
            LLMClient.from_settings(settings, prompt_version=EPICRISIS_PROMPT_VERSION),
        )
        request.app.state.llm_clients = clients
    return clients


LlmClientsDep = Annotated[LlmClients, Depends(get_llm_clients)]
