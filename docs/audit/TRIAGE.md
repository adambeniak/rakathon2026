# Štafeta — F0–F2 audit triage (Phase A)

Snapshot of 2026-10-17 ~01:30, `main` @ fd0af66 (#22). Read-only audit; no code was changed.
**Live index of the fixes = the pinned GitHub issue "P0 fix board".** This file is the evidence behind it.

## Sources and method
- Decision log: `docs/audit/decision-log-F0-F2.md` (authoritative 00:26 version incl. Phase C) and `BASE_PLAN.md` (the base).
  The log is not gospel: where `main` diverged for a documented, better reason the row is **KEEP** (see §Keep).
- 12 merged PRs (#1, #5, #10, #11, #12, #14, #17, #18, #19, #20, #21, #22), 0 closed-unmerged; PR bodies + comments;
  all review threads incl. Copilot (GraphQL); issues #2–#16; `git log origin/main`; unmerged branches (nothing
  important lives only there **except commit `253cabd`**, see EXT-3).
- Scattered notes: 112 notes in ~20 places (list in §Notes locations).
- Six read-only audit agents (infra/contracts, extraction+handover+consistency, referral+coordination+security,
  vector search, frontend, repo-wide notes sweep); every P0 claim re-checked by hand.
- Status: **DONE** (file:line) · **MISSING** · **CONTRADICTS** (both sides) · **N/A** · **KEEP** (main supersedes log).
- Priority: **P0** breaks demo steps 1–4, a non-negotiable, or security · **P1** diverges but works · **P2** polish.
- Owners per AGENTS.md repo map: P1 infra/IRIS/FHIR/vector · P2 extraction/handover/consistency · P3 frontend ·
  P4 domain/api/security/outputs/notify/e2e.

## Headline
1. **Backend works for steps 1, 2, 4 via the API**, but the demo breaks on: LLM cache not in the Docker image (EXT-2),
   no demo clock and no `mdt_start` for a live case (WF-2/WF-4/EXT-4), no C1/C2 conflicts → no "Nesouhlasí" (EXT-1),
   and an evidence-lock fix that never reached main (EXT-3).
2. **Frontend steps 1–4 work only on MSW mocks.** With `VITE_MOCKS=0`, steps 1, 2, 4 fail (wrong paths/bodies) and
   step 3 lacks per-value evidence chips, document upload and confirm/accept-missing (FE-1…12).
3. **Cross-cutting X1, X2, X4, X6, X7 are DONE.** X3 (ADR numbers) is polish. Docs claiming "demo mode defaults on"
   are stale (code defaults off — safer, keep).
4. Referral/coordination FHIR transactions were **never run against IRIS** (WF-1) — needs a human with `.iris/`.

## P0 — fix before F3 (each row = one GitHub issue)

| T | Fix | Owner | Rows merged | Evidence | Est. min |
|---|---|---|---|---|---|
| P0-1 | Restore date-quote evidence lock (cherry-pick `253cabd`) | P2 | EXT-3 | `backend/app/extraction/lock.py:192,252`; `253cabd` only on `origin/ai/extraction-core` (pushed 52 s after #11 merged); #11 thread `lock.py:251` "Fixed in 253cabd" | 15 |
| P0-2 | Ship the LLM cache in the backend image | P1 | EXT-2 | `extraction/llm.py:32` (cache under `REPO_ROOT/backend/tests/fixtures/llm_cache`); `backend/.dockerignore` excludes `tests/`; `backend/Dockerfile:25` copies only `app`; #11 thread `llm.py:32` | 25 |
| P0-3 | Demo clock + `mdt_start` required/persisted at pathway launch + handover `as_of` defaults to it | P4 | WF-2, WF-4, EXT-4, INF-15, FE-32 (backend half), K10 | no `/api/demo/advance`; `settings.py:112-116` static `STAFETA_DEMO_NOW`; FE `?today=` ignored (`frontend/src/lib/api/client.ts:14-19`); `routes/handover.py:89-91` as_of = now → Composition per minute (`fhir/mappers/handover.py:102`), never final; `fhir/referrals.py:126-136` no mdt_start; `api/services/coordination.py:202-204` English 422 | 90 |
| P0-4 | C1/C2 consistency rules wired via `findings=`, gate 14/15 (Closes #13) | P2 | EXT-1, NOTE-25 | `backend/app/consistency/__init__.py` docstring only; `routes/handover.py:112-122` no `findings=`; golden fields 7/14 expect `complete_with_conflict`; `tests/eval/handover_eval.py:35` `TODO(#13)` | 110 |
| P0-5 | Run `-m iris` integration tests on **local** IRIS (needs a human) | P1 | WF-1, K11, NOTE-15 | PR #17 "Not verified", PR #18 comment; `tests/integration/test_referral_flow.py:3-4`, `test_iris_coordination.py:3` | 30 |
| P0-6 | Prototype disclaimer footer | P3 | BASE-1 | BASE_PLAN §4.1 "Prototyp – fiktivní data, neurčeno pro klinické rozhodování" (Rakathon rule); absent from `frontend/src` | 10 |
| P0-7 | FE steps 1–2 wired to the contract (referral, claim, triage, findings) | P3 | FE-1, FE-2, FE-3, FE-4, INF-12, WF-3 | `features/referral/api.ts:6,9,15`; `features/cases/api.ts:24,53,60,65`; `Overview.tsx:17,37`; `TriagePanel.tsx:20` | 120 |
| P0-8 | FE step 3: per-value chips, upload, per-section confirm + accept-missing, remove "Potvrdit vše", AI-draft copy label, missing owner | P3 | FE-5, FE-6, FE-11, FE-12, FE-15, EXT-5 | `features/handover/api.ts:28,52,62`; `SectionCard.tsx:9-11,104-110`; `adapter.ts:50`; no upload UI | 120 |
| P0-9 | FE step 4: `/pathways` (+indicated_by, mdt_start), `/board`, task `/transitions` with place + date | P3 | FE-7, FE-8, FE-9 | `features/cases/api.ts:46,73,82`; `TasksBoard.tsx:40`; `lib/domain.ts:133` | 140 |

Decisions taken with the user (2026-10-17): `mdt_start` comes from pathway launch (not invented at referral);
"Potvrdit vše" is removed (per-section confirmation only); the team fixes in parallel from issues.

## Cross-cutting conventions X1–X12

| X | Verdict | Evidence |
|---|---|---|
| X1 one demo switch | DONE | `backend/app/settings.py:34` only `stafeta_demo_mode`; no `STAFETA_DEMO_AUTH`; `STAFETA_ENV` = deploy profile (KEEP) |
| X2 one `current_actor` | DONE | `security/actor.py:26-50`; `api/deps.py:43,46` (every route via `ActorDep`/`RepositoryDep`); CORS `main.py:105`; system actors are audited system writes (KEEP) |
| X3 ADR numbering | CONTRADICTS (P2) | two `docs/adr/0004-*`, `XXXX-coordination-api.md`, mixed `ADR-003`/`ADR-005` titles |
| X4 contracts/generated files | DONE | CI contract-drift step green (`ci.yml:44-48`); `schema.d.ts` regenerated in #21, all paths/schemas match. Missing: CI drift check for `schema.d.ts` (P2) |
| X5 shared ACI rules | DONE in code / no mechanism | idempotent seed `seed/loader.py:111-117`; reset cleans DocChunk `seed/__main__.py:55-67`; no guard against `demo-reset` on ACI (INF-14, P1) |
| X6 conftest guard | DONE | `backend/tests/conftest.py:16-42` |
| X7 HANDOFF union merge | DONE | `.gitattributes:1` |
| X8 unknown counts null | DONE | `routes/cases.py:177-188`; FE `CountBadge.tsx:5` |
| X9 FE never decides as-of | DONE (cases, handover) / CONTRADICTS (MDT, P1) | `Mdt.tsx:16,49`, `i18n/cs/common.ts:64` |
| X10 human force-pushes | N/A | process |
| X11 Copilot agent `-m "not iris"` | MISSING doc (P2) | `.github/copilot-instructions.md` has no rule |
| X12 big PRs | N/A | #5, #14, #17, #19, #20 > 400 lines (noted) |

## Infra / contracts / IRIS (owner P1 unless noted)

| T | Item | Status | Evidence | Prio | Fix | Min |
|---|---|---|---|---|---|---|
| INF-2 | Docs say demo mode "defaults to on" | CONTRADICTS (docs stale) | code default False `settings.py:35`; stale: `docs/known-issues.md:9` K1, `docs/security-privacy.md:25,27`, `docs/adr/XXXX-coordination-api.md:57`, `docs/HANDOFF.md:46` | P2 | fix docs, not code | 10 |
| INF-6 | Role mapping split between two FE clients | CONTRADICTS | `lib/api/client.ts:28` maps `physician→koc_physician`; `lib/api/http.ts:19` sends raw (→401 `actor.py:45-47`) | in P0-7 | share mapping / drop `http.ts` | 15 |
| INF-8 | ADR numbering (X3) | CONTRADICTS | see X3; vector ADR cited as 0004 in `retrieval/__init__.py:3`, `api/schemas/ask.py:1`, `retrieval/ask_lock.py:1`, `fhir-mapping.md:143` … | P2 | vector → 0006, coordination → 0007, update citations | 20 |
| INF-11 | No CI drift check for `schema.d.ts` | MISSING | `.github/workflows/ci.yml:52-80` | P2 | `pnpm gen:api && git diff --exit-code` | 10 |
| INF-12 | FE calls non-contract paths | CONTRADICTS | → P0-7/8/9 | P0 | — | — |
| INF-14 | No guard against reset/seed on shared ACI; `up-local` only redirects the container | MISSING | `Makefile:21,24,27,46` read the repo env file; PR #22 thread (log line 60); PR #5 "up-local untested" | P1 | `ENV_FILE ?=`; refuse `demo-reset` on non-local host unless `CONFIRM_SHARED=1` | 20 |
| INF-15 | Demo time helper | MISSING | → P0-3 | P0 | — | — |
| INF-18 | X11 rule missing in copilot-instructions | MISSING | `.github/copilot-instructions.md` | P2 | add line | 5 |
| INF-19..22 | Seed scenarios `story`/`demo-start`, reset keeps AuditEvents, RČ system `https://ncez.mzcr.cz/fhir/sid/rcis` | DONE | `seed/loader.py:6-8,143-209`; `Makefile:45-46`; `fhir/repository.py:209-237`; `fhir/systems.py:35-36` | — | — | — |
| INF-23 | RČ inside RelatedPerson/Coverage identifiers | open (#7) | `fhir/mappers/patient.py:87,111` | P1 | keep #7 | — |
| INF-24 | `make reindex` (log) vs `make index` | KEEP | `Makefile:26` | P2 | add `make index` row to AGENTS commands table | 3 |
| INF-25 | `make e2e` runs 0 tests (`frontend/e2e/` missing) | MISSING | `frontend/playwright.config.ts:5,8`; demo-script fallbacks rely on it | P1 (P4) | step 1–4 spec, real backend | — |
| INF-27 | CODEOWNERS placeholders | CONTRADICTS | `.github/CODEOWNERS:1-21` `@P1-handle`… | P2 | real logins | 5 |
| INF-28 | Phase C (Appendix A/B, CLAUDE.md, log location) | done in `fix/agent-conventions` | — | P1 | this PR | 15 |
| INF-29 | Untracked markers | P2 | `fhir/mappers/handover.py:355` `type: ignore` w/o issue; `settings.py:114` stale "P4 replaces with domain.clock" docstring; stray `frontend/PR_DESCRIPTION.md` | P2 | fix / delete | 10 |
| INF-30 | K1–K18 (`docs/known-issues.md`) and other notes not in issues | MISSING | Appendix A rule | P1 | mapped into the P1/P2 issues; then replace notes sections with issue links | 30 |
| INF-31 | No seeded reviewer (`X-Demo-Role: reviewer` → 401) | MISSING | `docs/vector-search.md:212`; `seed/demo_case.py` | P1 (step 6) | = WF-31 | 10 |
| INF-33 | PR #22 unresolved threads (4) | open | log line 60 (= INF-14), line 224 (`reindex`, log wrong), `BASE_PLAN.md:225` MDR wording, `BASE_PLAN.md:348` single i18n file (KEEP per-feature) | P2 | resolve | 10 |
| NOTE-1 | Plain `create` = write + AuditEvent in two calls (handover/coordination writes are atomic) | partly open | `fhir/repository.py:104-108`; #9 | P1 | narrow #9 | — |
| NOTE-2 | Failed/denied reads not audited | open | #8; `docs/security-privacy.md:40,49` | P1 | keep #8 | — |
| NOTE-13/14 | Our CodeSystems/extensions not loaded in IRIS; `$validate` never run | open | `docs/handover-open-items.md` O10, R11; `docs/fhir-mapping.md:80,151` | P1 | in extraction/handover P1 issue | — |
| NOTE-17 | `Settings.now()` should delegate to `domain.clock` | open | `docs/adr/0003…:30`; `settings.py:112-116` | in P0-3 | do it in P0-3 | — |
| NOTE-18 | fastembed model not pinned to revision/sha | open | `backend/Dockerfile:20`; vector-search.md #7 | P1 (security) | = VEC-11 | 20 |
| H-3 | Which ACI is live: log IP 57.174.97.175 vs repo DNS label | needs a human | `scripts/aci_up.sh:17`, `README.md:24`, env example line 14 | P1 | confirm, update docs | 5 |

## Extraction / handover / consistency (owner P2 unless noted)

| T | Item | Status | Evidence | Prio | Fix | Min |
|---|---|---|---|---|---|---|
| EXT-1 | C1/C2 rules | MISSING | → P0-4 | P0 | — | 110 |
| EXT-2 | LLM cache in image | MISSING | → P0-2 | P0 | — | 25 |
| EXT-3 | Date fact supported by its own quote | CONTRADICTS (fix lost) | → P0-1 | P0 | — | 15 |
| EXT-4 | as_of default = now; Composition per minute | CONTRADICTS | → P0-3 | P0 | — | — |
| EXT-5 | FE always `accept_missing:false`; `/confirm-all`, `/edit` 404 | CONTRADICTS | → P0-8 | P0 | — | — |
| EXT-6 | Per-value `items[]` with evidence {doc_id, quote, authored_at, received_at} | DONE | `domain/handover.py:173-195`; `contracts/handover.schema.json` `ItemEvidence` | — | — | — |
| EXT-7 | `missing_items` with owner (e-mail → coordinator, TNM/ECOG → KOC physician) | DONE | `domain/handover.py:147-152`; `extraction/handover/fields.py:296,348,523` | — | — | — |
| EXT-8 | `accepted_missing` requires a reason | MISSING | `domain/handover.py:161-170`; `routes/handover.py:59-79` | P1 | optional `reason`, required with `accept_missing` (additive) | 30 |
| EXT-9 | Composition stays `final` after a section reopens (R3) | open | `fhir/mappers/handover.py:493-501` | P2 | `amended` | 30 |
| EXT-10..13 | Idempotent persist; confirm via `current_actor` (works in demo mode); Provenance on confirm/edit; AuditEvent on reads | DONE | `fhir/handover_store.py:44-94`; `routes/handover.py:207,212`; `fhir/mappers/handover.py:505-530`; `fhir/cases.py:111-119`. HANDOFF "confirm always 403" is stale | — | — | — |
| EXT-14 | No per-case authorisation on handover routes | MISSING | `routes/handover.py:160,178,212,242` | P1 (security) | = WF-8 | 30 |
| EXT-15/16 | As-of: 12/13 excluded at 21. 10.; `doc_included(require_received=True)` | DONE | `extraction/lock.py:354-367`; `handover/service.py:66`; `tests/eval/test_handover_eval.py:3-4` | — | — | — |
| EXT-17 | Negation repair only with cue in quote | DONE | `lock.py:272-286` | — | — | — |
| EXT-18 | Quote repair NFKC (broader than sub/superscript) | KEEP | `lock.py:152-166`; `docs/extraction.md:307-308` | — | — | — |
| EXT-19 | `recommendation_or_plan` leftover in prompt file | P2 | `prompts/F1-3-extraction-core.md:26` | P2 | note as historical | 2 |
| EXT-20/21/23 | Cache key sha256(model+prompt+text); `Fact.specimen`; no findings stub, gate 13/15, `findings=` param | DONE | `llm.py:49-58`; `domain/evidence.py:85`; `assemble.py:71` | — | — | — |
| EXT-22 | Recall numbers (94.4 % → 52/54 → 53/54) | DONE | `docs/extraction.md:154,217,246` | P2 | pick one number for the pitch (53/54, tuned on the same 13 docs) | 2 |
| EXT-24 | Real epicrisis not recorded (fallback shown) | needs a human (H-2) | no `epicrisis-v1` cache entry; B5 | P1 | `STAFETA_LLM_CACHE=0 make eval`, verify, commit cache | 20 |
| EXT-25 | Step 3 statuses today: Chybí ECOG/TNM/e-mail with owner ✔, Zastaralé weight ✔ (`fields.py:577`), Nesouhlasí ✘ (EXT-1) — only if cache reachable (EXT-2) and uploads keep original file names (cache key = file stem, `documents/ingest.py:46-49`) | partial | — | → P0-2/P0-4 | demo checklist line | — |
| EXT-27 | Lab number may match the reference range in the row | open (#11 thread `lock.py:239`) | `lock.py:240` | P1 | bind to result cell | 45 |
| EXT-28 | Unit suffix match (`g/l` inside `mg/l`) | open (#11 thread `lock.py:242`) | `lock.py:246` | P1 | whole-token units | 20 |
| EXT-29 | Prompt says "keep the finding" vs negation convention → prompt v2 | open (#11 thread `prompt.py:33`) | `prompt.py:10` `extract-v1`; `docs/extraction.md:226`; O2/O3 | P1 | prompt v2 (specimen, typing errors, verbatim negation) | 45 |
| EXT-30 | Non-DOCX upload → GET handover 500 | MISSING | `handover/service.py:51`; `normalize.py:284`; uploads accept PDF `case_documents.py:35` | P1 | wrap / normalise PDF | 20 |
| EXT-32 | Open items R1–R11, O10–O15 | open | `docs/handover-open-items.md` | P1 (R5 depth limit, R11 `$validate`), P2 rest | issues | — |
| NOTE-30..37 | Recall miss 12.11; no held-out set; field 11/15 noise; heuristics may misfire on other cases; 8 negated facts still rejected (resectability); 30 dropped dates; safety follow-ups (cue proximity, UI reason for exclusions) | open | `docs/extraction.md:122-124,183,198,223,239-242,289-308`; `eval/report.json` (untracked) | P2 | extraction polish issue | — |
| NOTE-42/43 | GET/confirm and triage proposals re-run extraction per request | open | O15, R8; ADR-0005:36 | P2 | cache per (case, as_of) | — |

## Referral / coordination / security / domain (owner P4 unless noted)

| T | Item | Status | Evidence | Prio | Fix | Min |
|---|---|---|---|---|---|---|
| WF-1 | Transactions never run on IRIS | UNVERIFIED | → P0-5 | P0 | — | 30 |
| WF-2 | Demo time helper | MISSING | → P0-3 | P0 | — | — |
| WF-3 | FE steps 1, 2, 4 on mocks | MISSING | → P0-7/9 | P0 | — | — |
| WF-4 | Live case has no `mdt_start` | MISSING | → P0-3 | P0 | — | — |
| WF-5..7 | X1/X2 (one switch, one actor, every endpoint) | DONE | see X1/X2 | — | — | — |
| WF-8 | `authorize_case` missing on GET /cases, /cases/{id}, all handover routes | PARTIAL | `routes/cases.py:198,213`; `routes/handover.py:160,178`; applied in `fhir/workflow.py:133,223,243,322`, `fhir/triage.py:36`, `services/coordination.py:169`, `deps.py:150` | P1 (security) | add + widen #16 | 45 |
| WF-9..11, 13 | Histology due 19. 10. / sla 15. 10.; buckets; accept needs order_confirmed with place+date; events.py, case-states.md, ADR | DONE | `iris/fhir/plandefinition-pancreas-dx.json`; `domain/case.py:94-102`; `domain/task_machine.py:76-87`; `contracts/case-states.md` | — | — | — |
| WF-12 | `gp_opened`, `record_mdt_conclusion` (confirmed_by) etc. exist in domain but not in the API | MISSING | `fhir/workflow.py:39-41` `SUPPORTED_EVENTS`; ADR-0005:53 | P1 (steps 5–6) | endpoints | 90 |
| WF-14..19 | `/referrals/prefill`; size cap before parse (413 Czech); prefill audited; neutral 409; summary fields + null counts; If-Match / ifNoneExist in code | DONE | `routes/referrals.py:63,80`; `api/middleware.py:117-150`; `fhir/referrals.py:116-123,147-150` | — | — | — |
| WF-20 | Verb chains all-or-nothing, 409 names guard | DONE | `services/coordination.py:143-154,264-298` | — | — | — |
| WF-21 | Confirm without place falls back to template place | KEEP (plausible) | `task_machine.py:76`; `coordination.py:304-306` | P2 | optional: require place | 10 |
| WF-22 | One AuditEvent per save, not per machine event; no correlation id | CONTRADICTS | `coordination.py:290-297,334-343`; `fhir/tasks.py:240-275` | P1 (audit, decision) | ask before changing | 45 |
| WF-23, 25, 26, 27 | PlanDefinition owner roles; board lane; `indicated_by` → CarePlan.author + requester + Provenance, Czech 422; `eus-fnb` | DONE | `plandefinition-pancreas-dx.json`; `domain/board.py`; `coordination.py:133,192-199`; `fhir/tasks.py:150-213` | — | — | — |
| WF-24 | onBehalfOf is a display string, not an Organization ref | DONE (weaker) | `fhir/audit.py:67-68` | P2 | reference | 20 |
| WF-28 | Baton holder from two functions (summary vs board) | MISSING | `routes/cases.py:174`; `fhir/workflow.py:52-70`; `services/coordination.py:181`; K8 | P1 (visible in step 4) | derive from `board.build_board` | 45 |
| WF-29 | EpisodeOfCare.status not synced | open (#15) | `fhir/mappers/case.py:87` | P1 | keep #15 | 40 |
| WF-31 | No seeded reviewer | MISSING | `actor.py:22`; `seed/demo_case.py` | P1 (step 6) | seed reviewer for ZP 211 | 10 |
| WF-35 | Free-text postpone reason in AuditEvent | P2 | `case_machine.py:228-229` → `fhir/audit.py:96-101` | P2 | flag only | 15 |
| WF-36 | Launch without case-state check; no date ranges (K15) | P2 | `coordination.py:190-214` | P2 | guard | 20 |
| WF-37 | Watchdog `log.exception` may leak PHI in traceback | P2 | `api/watchdog.py:49,65` | P2 | `error_type` only | 5 |
| NOTE-59..71 | K2 role- not person-level ownership; K4 indicating physician never confirms; K5 no responsible physician on case; K7 failed step keeps SR active; K9 watchdog per replica + notify stub; K12 executionPeriod/owner display-only; K13 English `detail`; K14 surname in case id; K18 patient tasks no flow | open | `docs/known-issues.md`; `docs/adr/XXXX-coordination-api.md:59-75` | P2 | workflow polish issue | — |
| NOTE-75 | KOC 1 has no coordinator in the seed (422 if GP picks KOC 1) | open | `seed/demo_case.py:123-124` | P2 | demo note | — |

## Vector search / ask (owner P1)

| T | Item | Status | Evidence | Prio | Fix | Min |
|---|---|---|---|---|---|---|
| VEC-1/2/4 | Chunks ≤128 tokens/60 overlap, k=10, no header prefix | KEEP | `retrieval/embeddings.py:33-34`; `settings.py:79`; `docs/adr/0004-vector-search-and-ask.md:11-31`; `docs/vector-search.md:96-120` | — | — | — |
| VEC-3 | Chunk budgets are constants | P2 | `embeddings.py:33-36` | P2 | settings | 15 |
| VEC-5/7/12/14/16..20 | fastembed MiniLM 384 default; fake embedder in CI; per-sentence quote lock; "není uvedeno" wording; as-of filter; `authorize_case`; AuditEvent; no PHI in logs; HNSW latency table | DONE | `embeddings.py:68-121`; `tests/unit/retrieval/conftest.py:17-35`; `ask_lock.py:73-142`; `vector_store.py:93-109`; `deps.py:136-164`; `ask.py:154,176-185`; `vector-search.md:131-147` | — | — | — |
| VEC-6 | APIM selected by `EMBEDDING_PROVIDER`, env example comment suggests `EMBEDDING_MODEL` | CONTRADICTS | `settings.py:71`; env example lines 10-11 | P2 | fix comment / auto-select | 10 |
| VEC-8 | Dims only implicit in the column | PARTIAL | `vector_store.py:41-42,191`; `bootstrap_iris.py:37,148` | P2 | startup check | 15 |
| VEC-9 | Empty/mismatched index → confident "V dokumentaci … není uvedeno." | CONTRADICTS | `vector_store.py:109`; `ask.py:158,172-175` | P1 | 0 hits → 503 `index-empty` | 15 |
| VEC-10 | `make reindex` | KEEP (`make index`) | `Makefile:26` | — | — | — |
| VEC-11 | Model baked in, not pinned | PARTIAL | `backend/Dockerfile:18-23` | P1 (security) | pin revision / sha256 | 20 |
| VEC-13 | Advice prefix "Aplikace nedoporučuje léčbu…" reads as advising against treatment (no-answer variant worse) | needs decision | `retrieval/ask.py:39-40`; VS#2 | P1 | wording decision (clinical-safety-reviewer) | 5 |
| VEC-15 | Retrieval miss → false "není uvedeno" | open | VS#1; `ask.py:173-175` | P1 | full-context fallback before absence | 45 |
| VEC-23 | 7 Copilot threads on #20 | DONE in code | see §Review threads | P2 | resolve on GitHub | 5 |
| VEC-24/25 | Upload indexing not verified live; iFind failure silent | open | `indexing.py:156-165`; `search.py:172-174` | P2 | live check; health counter | 45 |
| VEC-26 | Image has no LLM cache → `/ask` 503 with `CACHE=1` (vs demo-script:115) | CONTRADICTS | VS#3; `vector-search.md:183-187` | P1 | resolved by P0-2 + ask fixtures in cache | 15 |
| NOTE-95 | No "Zeptat se případu" panel in FE | MISSING | HANDOFF:30 | P2 (stretch) | — | — |

## Frontend (owner P3)

| T | Item | Status | Evidence | Prio | Fix | Min |
|---|---|---|---|---|---|---|
| FE-1 | Step 1 referral: `/api/koc`, JSON `{filename}` instead of multipart `letter`, `submit.data.state` vs `ReferralCreated{case}`, no contact/phone/consent chips | CONTRADICTS | `features/referral/api.ts:6,9,15`; `Referral.tsx:24,42` | P0-7 | generated client + FormData, `/api/directory/kocs`, `ReferralPrefill` chips | 75 |
| FE-2 | Step 2 claim → `/claim` (not in contract), silent failure | CONTRADICTS | `cases/api.ts:53`; `CaseAction.tsx:14,20` | P0-7 | `/transitions {event:'accept'}` + problem title | 15 |
| FE-3 | Triage proposals/requests wrong shape; `/proposals` never called | CONTRADICTS | `cases/api.ts:60,65`; `TriagePanel.tsx:20` | P0-7 | `ProposalsOut` + `DocumentRequestsBody` | 45 |
| FE-4 | `/findings` not in contract → error box on every overview | MISSING | `cases/api.ts:24`; `Overview.tsx:17,37`; `SectionCard.tsx:156` | P0-7 | findings from `handover.findings` | 30 |
| FE-5 | No document upload (reports 01–06, 08–11) | MISSING | only `Referral.tsx:81` has a file input | P0-8 | upload on Dokumenty tab (`POST /api/cases/{id}/documents`) | 40 |
| FE-6 | Per-value evidence chips only on consent rows | MISSING | `SectionCard.tsx:104-110,169`; `adapter.ts:30` | P0-8 | chips per row | 20 |
| FE-7 | `/task-sets` instead of `/pathways` with `indicated_by`, `mdt_start` | CONTRADICTS | `cases/api.ts:73` | P0-9 | `LaunchPathwayRequest` + pre-filled physician | 40 |
| FE-8 | GET `/tasks` (not in contract); lanes `external` vs Role values | CONTRADICTS | `cases/api.ts:46`; `lib/domain.ts:133` | P0-9 | `GET /board` | 60 |
| FE-9 | "Potvrdit objednání" without place + date; `/phase` not in contract | MISSING | `TasksBoard.tsx:40`; `cases/api.ts:82` | P0-9 | form + `/api/tasks/{id}/transitions` | 40 |
| FE-10 | Section confirm with `expected_value_hash` | DONE | `handover/api.ts:26-28` | — | — | — |
| FE-11 | "Potvrdit vše" + inline edit → 404 | CONTRADICTS | `handover/api.ts:52,62`; `Handover.tsx:48` | P0-8 | **remove confirm-all** (decision); edit via `edited_value` | 30 |
| FE-12 | `missing_items[].suggested_owner` not shown | MISSING | `adapter.ts:50` | P0-8 | render owner | 15 |
| FE-13 | `accepted_missing` UI + reason | MISSING | `adapter.ts:53`; `api.ts:28` | P1 (needs EXT-8) | action + pill | 25 |
| FE-14 | Optimistic "Ověřeno lékařem" before server answers | P2 | `handover/api.ts:31-40` | P2 | "Ukládám…" | 10 |
| FE-15 | Copy section copies unlabelled AI draft | CONTRADICTS (non-negotiable 5) | `SectionCard.tsx:9-11` | P0-8 | "Návrh AI – nepotvrzeno" prefix | 5 |
| FE-16 | MDT as-of hard-coded | CONTRADICTS (X9) | `Mdt.tsx:16,49`; `i18n/cs/common.ts:64` | P1 (step 5) | from API | 15 |
| FE-17 | Consent detection by value regex | P2 | `adapter.ts:38` vs label `fields.py:788` | P2 | key on label | 5 |
| FE-18 | Unknown counts "—" | DONE | `CountBadge.tsx:5` | — | — | — |
| FE-19 | No MDT conclusion form; generate/send not role-gated | MISSING | `Mdt.tsx:76-83,144` | P1 (step 5) | `record_mdt_conclusion`, Lékař KOC only | 45 |
| FE-20 | GP "Potvrdit přijetí" state-driven but mock-only paths | DONE in UI / mock data | `Gp.tsx:18`; `gp/api.ts:4,12` | P1 (step 6) | `/cases` + `gp_opened` | 20 |
| FE-21 | `DEMO_USERS` (Havelka) ≠ seed (Hrubý) | CONTRADICTS | `mocks/fixtures/people.ts`; `AppShell.tsx:9`; `seed/demo_case.py:132` | P1 | users from directory/seed names | 15 |
| FE-22 | Stray `frontend/PR_DESCRIPTION.md` | P2 | — | P2 | delete | 2 |
| FE-23 | MSW handlers: 11 of 25 on contract paths | CONTRADICTS | `mocks/handlers/*` | with P0-7/8/9 | move to contract paths, typed | — |
| FE-24/25 | Hand-shaped fixtures; no zod at API boundaries | MISSING | `domain.ts:3`; `http.ts:31` | P1 | zod while rewiring | 20 |
| FE-29/30 | Mock triage includes 04; mock prefill quotes doc 08 | CONTRADICTS (mock) | `handlers/coordination.ts:21`; `handlers/portals.ts:32-34` | P2 | goes with P0-7 | — |
| FE-31 | Suspected diagnosis not shown | MISSING | `CaseDetail.suspected_diagnosis` unused | P1 | EvidenceChip slot | 20 |
| FE-32 | UI date switcher vs backend clock | CONTRADICTS | `client.ts:19`; `TasksBoard.tsx:22`; `BatonHolder.tsx:35` | P1 (after P0-3) | show backend demo time | 15 |
| FE-33 | T1–T3 placeholders, single edit-error flag, referral note, screenshots | open | `docs/frontend-wiring-todo.md:163-173` | P2 | polish issue | — |
| BASE-1 | Disclaimer footer | MISSING | BASE_PLAN §4.1 | P0-6 | — | 10 |

## §Keep — `main` supersedes the decision log / BASE_PLAN (do NOT "fix")
| Log / plan says | `main` does | Why keep | Evidence |
|---|---|---|---|
| Chunks ~450 chars / 80 overlap, k=8, context-header prefix | ≤128 model tokens / 60 overlap, k=10, header as `<chunk>` attributes | MiniLM reads 128 tokens; measured ranking better | ADR `0004-vector-search-and-ask.md:11-31`; `vector-search.md:96-120` |
| Demo mode implied on | `STAFETA_DEMO_MODE` defaults **off**, the env example sets 1 | fail-closed | `settings.py:35`; fix stale docs (INF-2) |
| `make reindex` | `make index` | used across docs/ADRs | `Makefile:26` |
| One env var | `STAFETA_ENV` kept as deploy-hardening profile | not an auth switch | `settings.py:99-107` |
| No SYSTEM fallback | `SYSTEM_ACTOR`, `WATCHDOG_ACTOR`, `SEED_ACTOR` for system writes | audited, never for user requests | `fhir/workflow.py:404-406`; `api/watchdog.py:28` |
| as-of: authored ≤ as_of | authored **before** the as-of day | stricter | `extraction/lock.py:362-363` |
| Quote repair only sub/superscript | NFKC fold, unique span, stored = source | documented | `docs/extraction.md:307-308` |
| 6 status values | 7 (`generated_with_citations`, `needs_clarification`) | mirrors golden | `domain/handover.py` |
| `findings=None` | `findings: Sequence[Finding] = ()` | same intent | `assemble.py:71` |
| Confirm by section | + `expected_value_hash`, changed section reopens | PR #19 review F5 | `routes/handover.py:71-74,218-219` |
| Every value quoted | physician-edited values have no doc quote | human-authored, labelled, Provenance | `extraction/handover/review.py:366-371` |
| — | CommunicationRequest without `intent` | correct for R4 | ADR-0005:66 |
| — | Case ids with hex suffix; uploads scoped by `encounter` | ADR-0005; meets #6 intent | `fhir/workflow.py:324-327` |
| Baton = step owner | coordinator keeps baton while a step is unordered / dependency failed | clinical-safety refinement | PR #17; `domain/board.py` |
| — | FE mocks on by default in dev; `http.ts` fallback; `today` query param | #21 review; documented | `frontend/src/main.tsx`; `client.ts:14-19` |
| BASE_PLAN: one `i18n/cs.ts` | one file per feature | fewer merge conflicts (AGENTS.md) | `frontend/src/i18n/cs/*` |
| BASE_PLAN: mock login with JWT | `X-Demo-Role` header in demo mode only | simpler, fail-closed | `security/actor.py` |

## Needs a human
- **H-1 (P0-5)** `make up-local && make iris-bootstrap && make seed` (local env), then `pytest -m iris tests/integration`.
- **H-2** `STAFETA_LLM_CACHE=0 make eval` to record the real epicrisis; verify offline; commit the cache.
- **H-3** Which ACI is live (IP vs DNS label); update the env example / README if needed.
- Decision: VEC-13 advice-prefix wording; WF-22 audit granularity.
- Demo: upload documents with their original file names (cache key = file stem).

## Review threads already fixed on `main` (resolve on GitHub)
26 unresolved threads, all verified fixed: #10 ×8 (FE-37), #12 ×3, #17 ×5, #18 ×all except CommunicationRequest.intent (KEEP),
#20 ×7 (VEC-23), #21 ×4 (FE-36). Still applying: #11 `lock.py:251` (P0-1), `llm.py:32` (P0-2), `lock.py:239` (EXT-27),
`lock.py:242` (EXT-28), `prompt.py:33` (EXT-29); #22 ×4 (INF-33).

## Notes locations (to migrate into issues, then replace with links)
`docs/HANDOFF.md` · `docs/known-issues.md` (K1–K18) · `docs/handover-open-items.md` (B/F/R/O) · `docs/vector-search.md`
§Known issues · `docs/extraction.md` (Runs, Open, failure modes) · `docs/frontend-wiring-todo.md` · `docs/security-privacy.md` ·
`docs/fhir-mapping.md` (§Deviations, §Later) · `docs/demo-script.md` (fallbacks) · ADR Consequences (0001, 0003, 0004 ×2,
0005, XXXX) · `contracts/case-states.md` · `frontend/PR_DESCRIPTION.md` · code comments (`tests/eval/handover_eval.py:35`,
`test_handover_eval.py:40`, `settings.py:49,113`, `handover/facts.py:38`, `api/schemas/cases.py:97-105`, `routes/handover.py:263`,
`fhir/workflow.py:38`, `api/watchdog.py:6`, `services/coordination.py:277`, `security/actor.py:6`, `docker-compose.yml:14`,
`app/{consistency,notify,outputs,timeline}/__init__.py`) · `// MOCK copy` markers in `frontend/src/mocks/fixtures/*` ·
PR bodies #5, #10, #14, #17, #18, #19, #20 · untracked `eval/report.json`.

## Issue housekeeping (recommendation — the human decides)
Close #2 and #3 (implemented in #12/#17: `domain/case_machine.py`, `task_machine.py`). Retitle #4 → "Real OIDC/SMART auth +
person-level task ownership (F4)" (mock login is done). Narrow #6 to the seed's global `ensure`. Narrow #9 to plain `create`.
Widen #16 with WF-8. Keep #7, #8, #13 (closed by P0-4), #15.

## Demo checklist (log §4) — status on `main`
| Step | API | UI (real backend) | Unblocked by |
|---|---|---|---|
| 1 Referral → Odesláno, Nový, baton Koordinátor KOC 2 | works (cache needed) | fails | P0-2, P0-7 (+P0-5) |
| 2 Převzít → triage 01, 02, 03, 05, 06 + hint cites 07 → request | works | fails | P0-7 (+P0-5) |
| 3 Handover 15 sections, chips, Chybí (owner), Nesouhlasí, Zastaralé, physician confirms | Nesouhlasí missing; confirm never final | partly | P0-1, P0-2, P0-3, P0-4, P0-8 |
| 4 Launch pathway (indicating physician) → board, baton, escalation 16. 10. | launch 422 on live case; no clock | fails | P0-3, P0-9 (+P0-5) |
| also | reports 12–13 excluded at 21. 10. ✔; `STAFETA_LLM_CACHE=1` needs P0-2 | | |
