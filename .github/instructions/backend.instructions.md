---
applyTo: "backend/**/*.py"
---
Follow `.claude/rules/backend.md` (full backend rules). Critical points:
- `domain/` is pure (no I/O, no FastAPI, no FHIR). Adapters live in `fhir/`, `iris/`, `extraction/`, `notify/`.
- Pydantic v2 models for every payload; RFC 7807 errors; async httpx with timeouts.
- LLM only via `app/extraction/llm.py`; every extracted value needs verbatim evidence.
- Never log PHI; every IRIS write goes through `app/fhir/repository.py` (writes AuditEvent).
- Add tests in `backend/tests/` and run `make check`.
