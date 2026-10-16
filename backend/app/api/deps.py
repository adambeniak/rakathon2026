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
from app.fhir.directory import DirectoryProvider
from app.fhir.handover_store import HandoverStore
from app.fhir.referrals import ReferralWriter
from app.fhir.repository import FhirRepository
from app.fhir.systems import DEMO_TAG_CODE
from app.fhir.triage import TriageReader
from app.fhir.workflow import CaseWorkflow, RequestWorkflow, authorize_case
from app.iris.db import IrisPool
from app.retrieval.ask import AskService
from app.retrieval.indexing import DocumentIndexer
from app.retrieval.search import HybridRetriever
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


def get_retriever(request: Request) -> HybridRetriever:
    retriever: HybridRetriever = request.app.state.retriever
    return retriever


def get_ask_llm(request: Request) -> LLMClient:
    llm: LLMClient = request.app.state.ask_llm
    return llm


class ParticipantCaseLocator:
    """Case -> (Task, Patient) for "ask the case", only for participants of the case.

    `/ask` returns document excerpts, so it is gated like triage (`authorize_case`): the referring GP or staff of
    the managing KOC; any other role (e.g. a reviewer) gets 403.
    """

    def __init__(self, reader: CaseReader, actor: PartyRef, directory: DirectoryProvider) -> None:
        self._reader = reader
        self._actor = actor
        self._directory = directory

    async def case_patient(self, case_id: str) -> tuple[str, str]:
        loaded = await self._reader.load(case_id)
        authorize_case(loaded, self._actor, await self._directory.get())
        return f"Task/{loaded.task['id']}", str(loaded.task["for"]["reference"])


def get_ask_service(
    reader: CaseReaderDep,
    repository: RepositoryDep,
    retriever: Annotated[HybridRetriever, Depends(get_retriever)],
    llm: Annotated[LLMClient, Depends(get_ask_llm)],
    actor: ActorDep,
    directory: DirectoryProviderDep,
    settings: SettingsDep,
) -> AskService:
    locator = ParticipantCaseLocator(reader, actor, directory)
    return AskService(locator, retriever, llm, repository, top_k=settings.ask_top_k, model=llm.model)


AskServiceDep = Annotated[AskService, Depends(get_ask_service)]


def get_document_indexer(request: Request, repository: RepositoryDep) -> DocumentIndexer:
    """Indexes uploaded documents into Stafeta.DocChunk; derived writes are audited as the current actor."""
    return DocumentIndexer(request.app.state.vector_store, request.app.state.embedder, repository)


DocumentIndexerDep = Annotated[DocumentIndexer, Depends(get_document_indexer)]
