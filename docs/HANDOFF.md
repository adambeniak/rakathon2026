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
- 2026-10-16 · Claude (P3 frontend shell) · fe/shell · `frontend/` shell: design system, 7 routes, MSW fixtures from golden file, tests green · next: wire `src/lib/api/http.ts` to the generated client once `contracts/openapi.json` exists (`pnpm gen:api`), then drop temporary types in `src/lib/domain.ts` · risks: no contract yet, mock endpoint paths are guesses
- 2026-10-16 · claude (wf) · wf/domain-logic · spikes/workflow: case+task machines, pathway, readiness gate, clock/workdays, PlanDefinition JSON, demo script; 145 tests green (`cd spikes/workflow && uv run --with pytest pytest`) · next: after P1 merge copy `spikes/workflow/domain/*.py` → `backend/app/domain/`, fix imports, `make check` + mypy strict, open PR · risks: new CodeSystems/extensions (`pathway-action`, `stafeta-role`, `StructureDefinition/{due-rule,sla-rule,place,owner-role,mdt-required-items}`) must be listed in docs/fhir-mapping.md (P1); histology task due 19. 10. vs SLA 15. 10. kept as separate fields
  (note: domain has 6 files incl. `events.py`+`__init__.py` beyond the 4 named in the brief; mypy --strict clean; tests/conftest PLAN_PATH uses parents[3] — adjust after move)
- 2026-10-16 · claude (P4) · wf/domain-logic · moved spike to backend/app/domain (case_machine, task_machine, pathway, clock, events); additive fields on Case/Task; contracts/case-states.md + ADR-003; `make check` backend green (247 tests), frontend step fails locally only for missing node_modules
  next: push + PR (user), API wiring: load PlanDefinition, build CaseContext, persist DomainEvents as AuditEvent; Settings.now() -> clock.now()
  risks: new FHIR code systems/extensions still to list in docs/fhir-mapping.md (P1); Case.baton_holder is cleared on role change (caller must reassign)
- 2026-10-16 · claude (P2 extraction) · ai/extraction-core · spikes/extraction: normalisation, strict-schema extraction, evidence lock (quote/term/number/unit/date/text/PS/negation/certainty), as-of filter, cached APIM client, golden atoms + eval with gates; 66 offline tests green (`make spike-extraction-test`); clinical-safety review applied
  Next: a human runs `make spike-extraction-fill-cache` (agents cannot use the env file) → `make spike-extraction-eval` → record first-run metrics in docs/extraction.md → extraction-auditor pass → after P1 merges backend/, move to backend/app/{documents,extraction} + tests/eval and open the PR.
  Risks: strict-mode anyOf may be rejected by the deployment (fallback in docs) · backend must call doc_included(require_received=True) · recall unknown until the first live run.
- 2026-10-16 · claude (P2 extraction) · ai/extraction-core · live run done; cache committed (14 responses). Run 1 recall 51/54; run 3 (after lock + audit fixes) 52/54, gates pass; audit blocker (negation convention) fixed in the lock
  Next: prompt v2 (negated value = copied negative clause, specimen on lab rows) + new live fill by a human; F2-2 must display negated values verbatim. Risks: lock tuned on the same 13 docs, no held-out set; see docs/extraction.md "Runs".
- 2026-10-16 · claude (P2 extraction) · ai/extraction-core · spike moved to backend/app/{documents,extraction} + tests/{unit,eval} + tests/fixtures/llm_cache; facts are P1's domain Fact (+ documented_plan, clinical_date_precision, specimen, quote_repaired, lock_notes); spikes/ and spike make targets removed
  `make eval` (cache only): 14/14 cache hits, 52/54, citations 100 %, 0 leakage with seed received_at + require_received=True; contracts unchanged. Next: F2-2 handover assembly on extract_case(); prompt v2 later. Risks: as above.
- 2026-10-16 · claude (P3 frontend) · fe/wiring-steps-1-4 · cases list/detail on generated client (+adapter, real state codes, null counts → '—'); triage checklist, task board, handover bar/edit/evidence panel, referral note on MSW mocks; lint/typecheck/build/53 tests green
  BLOCKED: referral, claim/transitions, document-requests, handover, task-sets/tasks are NOT in contracts/openapi.json (provisional paths in src/mocks/handlers + feature api.ts); backend was down, so steps 1–4 are unverified against the real API. Next: when F2 endpoints land → pnpm gen:api, replace http.ts calls, drop mocks. Risks: ux-reviewer had no browser (source review only); no postponed flag/stale count/diagnosis/KOC in contract
