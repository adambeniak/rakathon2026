"""Transaction Bundle assembly: urn:uuid fullUrls, conditional creates and optimistic locking in one place."""

from __future__ import annotations

import uuid
from typing import Any

from app.fhir.client import Resource


class BundleBuilder:
    def __init__(self) -> None:
        self._entries: list[dict[str, Any]] = []

    def post(self, resource: Resource, *, if_none_exist: str | None = None) -> str:
        """Add a create; returns the `urn:uuid:` that other entries use to reference it."""
        full_url = f"urn:uuid:{uuid.uuid4()}"
        request: dict[str, str] = {"method": "POST", "url": str(resource["resourceType"])}
        if if_none_exist:
            request["ifNoneExist"] = if_none_exist
        self._entries.append({"fullUrl": full_url, "resource": resource, "request": request})
        return full_url

    def put(self, resource: Resource, *, version_id: str | None = None) -> None:
        """Add an update of an existing resource; `version_id` makes it an optimistic-lock (If-Match) update."""
        request: dict[str, str] = {"method": "PUT", "url": f"{resource['resourceType']}/{resource['id']}"}
        if version_id:
            request["ifMatch"] = f'W/"{version_id}"'
        self._entries.append({"resource": resource, "request": request})

    def __len__(self) -> int:
        return len(self._entries)

    def build(self) -> Resource:
        return {"resourceType": "Bundle", "type": "transaction", "entry": list(self._entries)}
