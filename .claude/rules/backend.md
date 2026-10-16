---
paths:
  - "backend/**/*.py"
---
# Backend rules (Python 3.12, FastAPI)
- Layers: `api/` (HTTP only) → `domain/` (pure logic, no I/O) → adapters (`fhir/`, `iris/`, `extraction/`, `notify/`).
  `domain/` never imports from adapters or FastAPI.
- Every request/response body is a Pydantic v2 model; responses documented with examples (they feed `contracts/openapi.json`).
- Async everywhere (httpx.AsyncClient shared via lifespan). Timeouts on every outbound call.
- Settings via `pydantic-settings` (`app/settings.py`), read from env; never hardcode URLs or keys.
- LLM calls only through `app/extraction/llm.py` (single client, retry with backoff on 429, response cache, JSON-schema output).
- Errors: raise domain exceptions, map to RFC 7807 in `api/errors.py`. Never return stack traces.
- Logging: structlog/JSON; never log document text, names, RČ or other PHI — log IDs only.
- Every write to IRIS goes through `app/fhir/repository.py` which also writes the AuditEvent.
- Tests: `backend/tests/unit`, `backend/tests/integration` (`@pytest.mark.iris`), `backend/tests/eval`.
