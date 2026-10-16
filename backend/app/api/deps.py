"""FastAPI dependencies: settings, shared clients and adapters (created per request, cheap)."""

from __future__ import annotations

from typing import Annotated

import httpx
from fastapi import Depends, Request

from app.domain.common import PartyRef
from app.extraction.llm import LLMClient
from app.fhir.cases import CaseReader
from app.fhir.client import FhirClient
from app.fhir.repository import FhirRepository
from app.fhir.systems import DEMO_TAG_CODE
from app.iris.db import IrisPool
from app.retrieval.ask import AskService
from app.retrieval.search import HybridRetriever
from app.security.actor import current_actor
from app.settings import Settings


def get_settings(request: Request) -> Settings:
    settings: Settings = request.app.state.settings
    return settings


def get_http(request: Request) -> httpx.AsyncClient:
    http: httpx.AsyncClient = request.app.state.http
    return http


def get_iris_pool(request: Request) -> IrisPool:
    pool: IrisPool = request.app.state.iris_pool
    return pool


SettingsDep = Annotated[Settings, Depends(get_settings)]
ActorDep = Annotated[PartyRef, Depends(current_actor)]
IrisPoolDep = Annotated[IrisPool, Depends(get_iris_pool)]


def get_fhir_client(settings: SettingsDep, http: Annotated[httpx.AsyncClient, Depends(get_http)]) -> FhirClient:
    return FhirClient(http, settings.fhir_base_url, settings.iris_user, settings.iris_password)


FhirClientDep = Annotated[FhirClient, Depends(get_fhir_client)]


def get_repository(client: FhirClientDep, actor: ActorDep, settings: SettingsDep) -> FhirRepository:
    return FhirRepository(client, actor, tag_code=DEMO_TAG_CODE if settings.stafeta_demo_mode else None)


RepositoryDep = Annotated[FhirRepository, Depends(get_repository)]


def get_case_reader(repository: RepositoryDep) -> CaseReader:
    return CaseReader(repository)


CaseReaderDep = Annotated[CaseReader, Depends(get_case_reader)]


def get_retriever(request: Request) -> HybridRetriever:
    retriever: HybridRetriever = request.app.state.retriever
    return retriever


def get_ask_llm(request: Request) -> LLMClient:
    llm: LLMClient = request.app.state.ask_llm
    return llm


def get_ask_service(
    reader: CaseReaderDep,
    repository: RepositoryDep,
    retriever: Annotated[HybridRetriever, Depends(get_retriever)],
    llm: Annotated[LLMClient, Depends(get_ask_llm)],
    settings: SettingsDep,
) -> AskService:
    return AskService(reader, retriever, llm, repository, top_k=settings.ask_top_k, model=llm.model)


AskServiceDep = Annotated[AskService, Depends(get_ask_service)]
