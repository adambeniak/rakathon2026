"""Async FHIR R4 HTTP client for IRIS for Health (owner: P1).

Thin transport layer: base URL + basic auth from settings, `application/fhir+json`, OperationOutcome -> typed
exceptions, retries for reads only. Use `app.fhir.repository.FhirRepository` for writes (demo tag + AuditEvent).
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Any

import httpx
import structlog
from pydantic import SecretStr
from tenacity import AsyncRetrying, retry_if_exception_type, stop_after_attempt, wait_exponential

from app.fhir.errors import FhirError, FhirUnavailableError, OutcomeIssue, error_for_status

FHIR_JSON = "application/fhir+json"
Resource = dict[str, Any]
SearchParams = Mapping[str, str | Sequence[str]]

log = structlog.get_logger(__name__)


@dataclass(frozen=True)
class CreateResult:
    """Outcome of a (conditional) create. `created` is False when If-None-Exist matched an existing resource."""

    resource_type: str
    id: str
    created: bool

    @property
    def reference(self) -> str:
        return f"{self.resource_type}/{self.id}"


def reference_from_location(location: str) -> tuple[str, str]:
    """'http://h/fhir/r4/Patient/12/_history/1' or 'Patient/12' -> ('Patient', '12')."""
    parts = [p for p in location.split("?")[0].split("/") if p]
    if "_history" in parts:
        parts = parts[: parts.index("_history")]
    if len(parts) < 2:
        raise ValueError("location does not contain a resource reference")
    return parts[-2], parts[-1]


class FhirClient:
    def __init__(
        self,
        http: httpx.AsyncClient,
        base_url: str,
        user: str,
        password: SecretStr,
        *,
        read_attempts: int = 3,
    ) -> None:
        self._http = http
        self._base = base_url.rstrip("/")
        self._auth = httpx.BasicAuth(user, password.get_secret_value())
        self._read_attempts = read_attempts

    # --- reads (retried on FhirUnavailableError) ---

    async def capabilities(self) -> Resource:
        return await self._get_json("metadata")

    async def read(self, resource_type: str, resource_id: str) -> Resource:
        return await self._get_json(f"{resource_type}/{resource_id}")

    async def search(self, resource_type: str, params: SearchParams) -> Resource:
        """One page of a search (a searchset Bundle)."""
        return await self._get_json(resource_type, params=params)

    async def search_all(self, resource_type: str, params: SearchParams, *, max_pages: int = 50) -> list[Resource]:
        """All `match` entries of a search, following `next` links."""
        bundle = await self.search(resource_type, params)
        resources = _matches(bundle)
        for _ in range(max_pages - 1):
            next_url = _next_link(bundle)
            if next_url is None:
                return resources
            bundle = await self._get_json(next_url)
            resources.extend(_matches(bundle))
        raise FhirError(f"search {resource_type} exceeded {max_pages} pages")

    async def count(self, resource_type: str, params: SearchParams) -> int:
        bundle = await self.search(resource_type, {**params, "_summary": "count"})
        return int(bundle.get("total", 0))

    # --- writes (never retried automatically) ---

    async def create(self, resource: Resource, *, if_none_exist: str | None = None) -> CreateResult:
        resource_type = str(resource["resourceType"])
        headers = {"If-None-Exist": if_none_exist} if if_none_exist else {}
        response = await self._send("POST", resource_type, json=resource, headers=headers)
        location = response.headers.get("location") or response.headers.get("content-location")
        if not location:
            raise FhirError(f"POST {resource_type} returned no Location header", status_code=response.status_code)
        found_type, found_id = reference_from_location(location)
        return CreateResult(found_type, found_id, created=response.status_code == httpx.codes.CREATED)

    async def update(self, resource: Resource) -> Resource:
        path = f"{resource['resourceType']}/{resource['id']}"
        response = await self._send("PUT", path, json=resource, headers={"Prefer": "return=representation"})
        return _json_or_empty(response)

    async def delete(self, resource_type: str, resource_id: str) -> None:
        await self._send("DELETE", f"{resource_type}/{resource_id}")

    async def transaction(self, bundle: Resource) -> Resource:
        if bundle.get("resourceType") != "Bundle" or bundle.get("type") not in ("transaction", "batch"):
            raise ValueError("transaction() expects a Bundle of type transaction or batch")
        response = await self._send("POST", "", json=bundle)
        return _json_or_empty(response)

    # --- internals ---

    async def _get_json(self, path_or_url: str, *, params: SearchParams | None = None) -> Resource:
        retrying = AsyncRetrying(
            retry=retry_if_exception_type(FhirUnavailableError),
            stop=stop_after_attempt(self._read_attempts),
            wait=wait_exponential(multiplier=0.5, max=4),
            reraise=True,
        )
        response: httpx.Response = await retrying(self._send, "GET", path_or_url, params=params)
        return _json_or_empty(response)

    async def _send(
        self,
        method: str,
        path_or_url: str,
        *,
        params: SearchParams | None = None,
        json: Resource | None = None,
        headers: Mapping[str, str] | None = None,
    ) -> httpx.Response:
        if path_or_url.startswith(("http://", "https://")):
            url = _same_origin(path_or_url, self._base)
        else:
            url = f"{self._base}/{path_or_url}" if path_or_url else self._base
        label = f"{method} {_resource_path(url, self._base)}"
        request_headers = {"Accept": FHIR_JSON, **(headers or {})}
        if json is not None:
            request_headers["Content-Type"] = FHIR_JSON
        try:
            response = await self._http.request(
                method, url, params=params, json=json, headers=request_headers, auth=self._auth
            )
        except httpx.TransportError as exc:
            raise FhirUnavailableError(f"{label}: {type(exc).__name__}") from exc
        if response.is_success:
            return response
        issues = _outcome_issues(response)
        # Codes and FHIRPath expressions only: diagnostics may quote the offending value (PHI).
        log.warning(
            "fhir_request_failed",
            request=label,
            status=response.status_code,
            issue_codes=[i.code for i in issues],
            issue_expressions=[list(i.expression) for i in issues],
        )
        raise error_for_status(f"{label} -> HTTP {response.status_code}", response.status_code, issues)


def _same_origin(url: str, base: str) -> str:
    """Paging links are absolute: never send credentials to another origin than the configured FHIR base."""
    target, expected = httpx.URL(url), httpx.URL(base)
    if (target.scheme, target.host, target.port) != (expected.scheme, expected.host, expected.port):
        raise FhirError("FHIR server returned a link to a different origin; refusing to follow it")
    return url


def _resource_path(url: str, base: str) -> str:
    """Path relative to the FHIR base without the query string (it may contain identifiers)."""
    path = url.split("?", 1)[0]
    if path.startswith(base):
        return path[len(base) :].lstrip("/") or "/"
    return httpx.URL(path).path


def _json_or_empty(response: httpx.Response) -> Resource:
    if not response.content:
        return {}
    data = response.json()
    if not isinstance(data, dict):
        raise FhirError("FHIR server returned a non-object JSON body", status_code=response.status_code)
    return data


def _outcome_issues(response: httpx.Response) -> list[OutcomeIssue]:
    try:
        data = response.json()
    except ValueError:
        return []
    if not isinstance(data, dict) or data.get("resourceType") != "OperationOutcome":
        return []
    return [OutcomeIssue.from_json(issue) for issue in data.get("issue", []) if isinstance(issue, dict)]


def _matches(bundle: Resource) -> list[Resource]:
    return [
        entry["resource"]
        for entry in bundle.get("entry", [])
        if "resource" in entry and entry.get("search", {}).get("mode", "match") == "match"
    ]


def _next_link(bundle: Resource) -> str | None:
    for link in bundle.get("link", []):
        if link.get("relation") == "next" and link.get("url"):
            return str(link["url"])
    return None
