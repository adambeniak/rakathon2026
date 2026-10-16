# Handoff log

Newest at the bottom. Max 5 lines per entry: time · who/agent · branch · done · next · risks.

- 2026-10-16 16:00 · starter kit · main · repo initialised from starter kit · F1 foundation (prompts/F1-*.md) · none yet
- 2026-10-16 17:50 · Claude (P1 env check) · main · APIM OK: `gpt-6-1-sol-dz-eu` HTTP 200; `LLM_MODEL_FAST` not set (untested).
  ACI recreated with DNS label: update `.env` to `IRIS_HOST=stafeta-team73.swedencentral.azurecontainer.io` and `FHIR_BASE_URL=http://stafeta-team73.swedencentral.azurecontainer.io:52773/fhir/r4` (old IP is dead).
  `$zv` = IRIS for UNIX (Ubuntu Server LTS for x86-64 Containers) 2026.1 (Build 235U); FHIRSERVER + /fhir/r4, metadata
  HTTP 200 (data endpoints 401 without auth); Stafeta.DocChunk + HNSW index created; no password-file errors in logs.
  Next: F1, `make seed`. Risks: ACI non-persistent (restart = bootstrap+seed) · `make up` needs local IRIS (mailpit-only target for P4).
- 2026-10-16 18:45 · Claude (P1, F1-1) · be/foundation (PR #5) · backend skeleton, FHIR repo + AuditEvent, seed (story/demo-start), contracts, docs/ADRs;
  ACI seeded (story: case `rakathon-2026-prochazkova`, pripraveno_mdt, 13 docs); `make up` = backend+mailpit vs ACI, `make up-local` adds IRIS.
  Next: merge PR #5 → P2 moves extraction into backend/app, P3 runs `make contract` (gen:api), P4 starts #2/#3/#4 on app/domain.
  Risks: write+audit not atomic · API has no auth (#4), compose binds 127.0.0.1 · local IRIS fallback untested (F4) ·
  ACI restart = `make iris-bootstrap && make seed` · demo step 1 needs `make demo-reset` (directory + patient only).
