"""The only write path to IRIS FHIR (owner: P1).

Every write is stamped with the demo tag (in demo mode) and followed by an `AuditEvent` naming the actor and the
written resources. Reads of clinical content are audited explicitly via `audit_read`. Write + audit are two HTTP
calls (not atomic): if the audit fails, `AuditWriteError` is raised with the reference of the written resource.
"""

from __future__ import annotations

import copy
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from datetime import UTC, datetime

import structlog

from app.domain.common import PartyRef
from app.fhir.audit import AuditAction, AuditSubtype, build_audit_event
from app.fhir.client import CreateResult, FhirClient, Resource, SearchParams, reference_from_location
from app.fhir.errors import AuditWriteError, FhirConflictError, FhirError
from app.fhir.systems import CS_TAG, DEMO_TAG_CODE

log = structlog.get_logger(__name__)

# Max entities per summary AuditEvent written by delete_by_tag.
AUDIT_CHUNK = 100


@dataclass(frozen=True)
class EnsureResult:
    resource_type: str
    id: str
    created: bool

    @property
    def reference(self) -> str:
        return f"{self.resource_type}/{self.id}"


def _utc_now() -> datetime:
    return datetime.now(UTC)


def primary_identifier(resource: Resource) -> tuple[str, str]:
    """The first identifier is the business key used for idempotent (conditional) creates."""
    identifiers = resource.get("identifier") or []
    first = identifiers[0] if isinstance(identifiers, list) and identifiers else {}
    if "system" not in first or "value" not in first:
        raise ValueError(f"{resource.get('resourceType')} needs identifier[0] with system and value")
    return str(first["system"]), str(first["value"])


class FhirRepository:
    def __init__(
        self,
        client: FhirClient,
        actor: PartyRef,
        *,
        tag_code: str | None = DEMO_TAG_CODE,
        clock: Callable[[], datetime] = _utc_now,
    ) -> None:
        """`tag_code=None` disables tagging (production); tests use `stafeta-test` to clean up after themselves."""
        self.client = client
        self.actor = actor
        self.tag_code = tag_code
        self._clock = clock

    # --- reads ---

    async def read(self, resource_type: str, resource_id: str) -> Resource:
        return await self.client.read(resource_type, resource_id)

    async def search(self, resource_type: str, params: SearchParams) -> list[Resource]:
        return await self.client.search_all(resource_type, params)

    async def count(self, resource_type: str, params: SearchParams) -> int:
        return await self.client.count(resource_type, params)

    async def find_by_identifier(self, resource_type: str, system: str, value: str) -> Resource | None:
        found = await self.client.search_all(resource_type, {"identifier": f"{system}|{value}"})
        if len(found) > 1:
            raise FhirConflictError(f"{resource_type} identifier {system} is not unique ({len(found)} matches)")
        return found[0] if found else None

    async def audit_read(self, entities: Sequence[str], *, subtype: AuditSubtype = "read") -> None:
        """Record that the current actor read clinical content (AGENTS.md non-negotiable 6).

        FHIR R4 AuditEventAction: a search/query is `E` (execute), a read of identified resources is `R`.
        """
        await self._audit("E" if subtype == "search-type" else "R", subtype, entities)

    async def audit_derived_write(self, entities: Sequence[str], *, description: str) -> None:
        """Record a write of data derived from these resources outside FHIR (e.g. vector-index rows in IRIS SQL)."""
        await self._audit("C", "create", entities, description=description)

    # --- writes ---

    async def create(self, resource: Resource, *, if_none_exist: str | None = None) -> CreateResult:
        result = await self.client.create(self._tagged(resource), if_none_exist=if_none_exist)
        if result.created:
            await self._audit("C", "create", [result.reference])
        return result

    async def ensure(self, resource: Resource) -> EnsureResult:
        """Idempotent create keyed by `identifier[0]`: no write (and no AuditEvent) if it already exists."""
        resource_type = str(resource["resourceType"])
        system, value = primary_identifier(resource)
        existing = await self.find_by_identifier(resource_type, system, value)
        if existing is not None:
            return EnsureResult(resource_type, str(existing["id"]), created=False)
        result = await self.create(resource, if_none_exist=f"identifier={system}|{value}")
        return EnsureResult(result.resource_type, result.id, created=result.created)

    async def update(self, resource: Resource) -> Resource:
        if "id" not in resource:
            raise ValueError("update() needs a resource with an id")
        updated = await self.client.update(self._tagged(resource))
        await self._audit("U", "update", [f"{resource['resourceType']}/{resource['id']}"])
        return updated

    async def delete(self, resource_type: str, resource_id: str) -> None:
        await self.client.delete(resource_type, resource_id)
        await self._audit("D", "delete", [f"{resource_type}/{resource_id}"])

    async def transaction(self, bundle: Resource) -> Resource:
        """Atomic multi-resource write. One AuditEvent lists every entry that was actually written."""
        for entry in bundle.get("entry", []):
            request = entry.get("request", {})
            if request.get("method") == "DELETE" and "?" in str(request.get("url", "")):
                raise ValueError("conditional DELETE in a transaction is not supported (its target cannot be audited)")
        tagged = copy.deepcopy(bundle)
        for entry in tagged.get("entry", []):
            if "resource" in entry:
                entry["resource"] = self._tagged(entry["resource"])
        response = await self.client.transaction(tagged)
        written = _written_references(tagged, response)
        if written:
            await self._audit("E", "transaction", written)
        return response

    async def delete_by_tag(self, resource_types: Sequence[str], tag_code: str) -> dict[str, int]:
        """Delete every resource carrying `tag_code`, in the given order (dependents first).

        The audit trail is never deleted (AuditEvent is refused). Writes summary AuditEvents (one per `AUDIT_CHUNK`
        deleted resources) instead of one per resource — also when the reset aborts halfway, so every deletion that
        happened is audited. Used by `python -m app.seed --reset` and the integration tests.
        """
        if "AuditEvent" in resource_types:
            raise ValueError("AuditEvents are never deleted (AGENTS.md non-negotiable 6)")
        deleted: dict[str, int] = {}
        references: list[str] = []
        try:
            for resource_type in resource_types:
                query = {"_tag": f"{CS_TAG}|{tag_code}", "_count": "100"}
                found = await self.client.search_all(resource_type, query)
                for resource in found:
                    await self.client.delete(resource_type, str(resource["id"]))
                    references.append(f"{resource_type}/{resource['id']}")
                deleted[resource_type] = len(found)
        finally:
            for start in range(0, len(references), AUDIT_CHUNK):
                await self._audit(
                    "D",
                    "delete",
                    references[start : start + AUDIT_CHUNK],
                    description=f"reset of tag {tag_code}: {len(references)} resources",
                )
        return deleted

    # --- internals ---

    def _tagged(self, resource: Resource) -> Resource:
        if self.tag_code is None:
            return resource
        tagged = copy.deepcopy(resource)
        tags = tagged.setdefault("meta", {}).setdefault("tag", [])
        if not any(t.get("system") == CS_TAG and t.get("code") == self.tag_code for t in tags):
            tags.append({"system": CS_TAG, "code": self.tag_code})
        return tagged

    async def _audit(
        self, action: AuditAction, subtype: AuditSubtype, entities: Sequence[str], *, description: str | None = None
    ) -> None:
        event = build_audit_event(
            action=action,
            subtype=subtype,
            actor=self.actor,
            entities=entities,
            recorded=self._clock(),
            description=description,
        )
        try:
            await self.client.create(self._tagged(event))
        except FhirError as exc:
            log.error("audit_write_failed", action=action, subtype=subtype, entities=list(entities)[:20])
            raise AuditWriteError(
                f"AuditEvent for {action} {list(entities)[:5]} not stored", status_code=exc.status_code
            ) from exc


def _written_references(request_bundle: Resource, response_bundle: Resource) -> list[str]:
    """References of entries that changed data.

    A conditional create that matched (POST + 200) and reads (GET) are not writes. A DELETE may answer 204 without
    `location`: its target comes from the request URL (conditional deletes are refused before submitting).
    """
    references: list[str] = []
    requests = request_bundle.get("entry", [])
    for index, entry in enumerate(response_bundle.get("entry", [])):
        response = entry.get("response", {})
        status = str(response.get("status", "")).split(" ", 1)[0]
        request = requests[index].get("request", {}) if index < len(requests) else {}
        method = request.get("method")
        if not status.startswith("2") or method == "GET" or (method == "POST" and status == "200"):
            continue
        location = response.get("location")
        if location:
            resource_type, resource_id = reference_from_location(str(location))
            references.append(f"{resource_type}/{resource_id}")
        elif method == "DELETE" and request.get("url"):
            references.append(str(request["url"]).strip("/"))
    return references
