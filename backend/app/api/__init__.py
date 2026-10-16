"""HTTP layer only: routers, request/response schemas, RFC 7807 errors (owner: P4; scaffold by P1).

Routers live in `app.api.routes.<feature>` and are auto-discovered; each module exposes `router: APIRouter`.
No business logic here: call `app.domain` and the adapters (`app.fhir`, `app.iris`, `app.extraction`).
"""
