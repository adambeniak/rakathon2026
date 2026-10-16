"""Request-scoped building blocks shared by `api.deps` and `security.actor` (kept apart to avoid an import cycle)."""

from __future__ import annotations

from typing import Annotated

import httpx
from fastapi import Depends, Request

from app.fhir.client import FhirClient
from app.fhir.directory import DirectoryProvider
from app.settings import Settings


def get_settings(request: Request) -> Settings:
    settings: Settings = request.app.state.settings
    return settings


def get_http(request: Request) -> httpx.AsyncClient:
    http: httpx.AsyncClient = request.app.state.http
    return http


SettingsDep = Annotated[Settings, Depends(get_settings)]


def get_fhir_client(settings: SettingsDep, http: Annotated[httpx.AsyncClient, Depends(get_http)]) -> FhirClient:
    return FhirClient(http, settings.fhir_base_url, settings.iris_user, settings.iris_password)


FhirClientDep = Annotated[FhirClient, Depends(get_fhir_client)]


def get_directory_provider(client: FhirClientDep) -> DirectoryProvider:
    return DirectoryProvider(client)


DirectoryProviderDep = Annotated[DirectoryProvider, Depends(get_directory_provider)]
