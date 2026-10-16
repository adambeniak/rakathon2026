# Štafeta — decision log & audit brief (F0–F2)

Written 2026-10-16 ~22:45 by P1's planning assistant (Claude chat), for an audit/fix agent with `gh` access.
Source of truth order: **AGENTS.md → this log → prompts/*.md → docs/**. If the repo contradicts this log,
the repo may be right (a decision may have been changed later) — report it, do not silently "fix" it.

> Important: P1 did not relay every item below to P2–P4. Treat each item as the **intended state**, verify it
> in the repo, and classify it. Some items may already be done, some never reached the agents.

---

## 0. Instructions for the audit agent

### Phase A — triage only (max 45 min, read-only)
1. Inventory. All work is already merged into `main` (no open PRs); audit the **merged/closed PRs** and the code on `main`:
   - `gh pr list --state merged --limit 100` and `gh pr list --state closed --limit 100`
   - for every merged PR: `gh pr view <n> --comments` — read the description sections "not done", "risks",
     "deviations", "follow-ups", and every review comment;
   - **unresolved review threads incl. Copilot** (merged PRs often have them):
     `gh api graphql -f query='query{repository(owner:"adambeniak",name:"rakathon2026"){pullRequests(states:MERGED,first:50){nodes{number title reviewThreads(first:100){nodes{isResolved path line comments(first:3){nodes{author{login} body}}}}}}}}'`
     → for each unresolved thread check on `main` whether it still applies;
   - `gh issue list --state all`, `git log --oneline origin/main -80`, `docs/HANDOFF.md`, `docs/adr/`, `contracts/`,
     `docs/extraction.md`, `docs/security-privacy.md`, `docs/fhir-mapping.md`.
   - Check the code on `main`, not the PR diffs — later PRs may have changed or fixed things.
   - **Notes are scattered** — each agent recorded known issues in a different place. Sweep all of them:
     ```bash
     # any markdown that may hold notes, handoffs, follow-ups
     git ls-files '*.md' | grep -viE 'node_modules|CHANGELOG' 
     # sections and markers agents used
     git grep -nIiE 'not done|known (issue|risk|gap)|follow[- ]?up|deferred|out of scope|limitation|tech debt|open question|needs (you|input|P[1-4])|blocked|workaround|fallback|placeholder|stub|mock copy|demo rule|temporary|later' -- '*.md'
     git grep -nIE 'TODO|FIXME|XXX|HACK|NOTE\(|TODO\(#' -- backend frontend iris scripts contracts
     # skipped / expected-to-fail tests and disabled checks
     git grep -nIE 'pytest\.mark\.(skip|xfail)|@skip|\.skip\(|test\.fixme|it\.todo|# type: ignore|eslint-disable|noqa' -- backend frontend
     # ADR consequences / follow-ups, eval reports, leftovers
     ls docs docs/adr docs/audit frontend/docs eval 2>/dev/null; git ls-files | grep -iE 'handoff|notes|todo|report|spikes/|worktrees'
     git log origin/main --format='%h %s%n%b' -80 | grep -iE 'wip|known|todo|follow|defer|fix later|temporary'
     ```
     Also read: every ADR's "Consequences"/"Follow-ups", `docs/extraction.md` ("Runs", failure modes),
     `eval/report.json`, PR bodies, issue bodies. Merge everything into TRIAGE.md with the source (file:line / PR# / issue#).
   - Agents' final chat reports were NOT committed. P1 may paste the ones he still has into `docs/audit/agent-reports.md`
     before you start — read it if it exists.
2. For every item in sections 2–6 decide: **DONE** (show file:line) · **MISSING** · **CONTRADICTS** (show both) ·
   **N/A** (superseded — explain).
3. Add any other divergence from the prompts / AGENTS.md / demo-flow skill you find.
4. Write `docs/audit/TRIAGE.md` with one table per area and a priority per row:
   - **P0** — breaks a demo step 1–4, violates an AGENTS.md non-negotiable (fictitious data, evidence lock,
     no clinical advice, as-of, human in loop, audit) or is a security hole. Fix before F3.
   - **P1** — diverges from a decision but works. Becomes an issue for F3/F4 with owner.
   - **P2** — polish. Issue, label `polish`.
5. STOP and show P1 the P0 list. Do not change code in Phase A.

### Phase B — fixes (after P1 approves the P0 list)
You are the ONLY session working on the repo during this phase (the team is paused), so you fix across all areas.
1. Everything is on `main`. Work in **small PRs per topic** from fresh `main` (`fix/<topic>`), merged one by one
   (always branch from the latest `main` after the previous merge — no stacking).
2. Order: cross-cutting first (X1 env var, X2 actor, X6 conftest guard, X3 ADR numbers, X4 contract regen),
   then backend per area (handover/extraction, referral, coordination, vector search), then frontend.
3. After each merged backend PR: `make contract`, then `pnpm gen:api` in frontend, commit generated files.
4. End of Phase B: run demo checklist (section 4) locally against local IRIS (`make up-local`, `seed --scenario
   demo-start`), report pass/fail per step, write `docs/audit/RESULT.md` and 5 lines in `docs/HANDOFF.md`.
- Never revert an approved deviation (section 3), never make a contract change that is not additive,
  never refactor for style, never touch `data/golden/`, never run tests marked `iris` against the shared ACI.
- Every fix PR: `make check` green, Conventional Commit title, "Closes #n". The human pushes after rebases
  (`--force-with-lease`) and merges.
- P1/P2 items are NOT fixed now: create issues with owner prefix (`[P2] …`) and phase (`F3`/`F4`).
- Timebox: Phase A 45 min, Phase B P0 fixes max ~2 h. If P0 fixes exceed that, stop and report what remains.

### Phase C — make the flow stick (first fix PR, `fix/agent-conventions`, ~15 min)
So that F3/F4 agents report and behave the same way:
1. Add the section from **Appendix A** to `AGENTS.md` (keep the file under ~200 lines; condense elsewhere if needed).
2. Add `.github/pull_request_template.md` from **Appendix B**.
3. In `CLAUDE.md` → "Session end": "Fill the PR template sections; every 'Not done' item becomes a GitHub issue
   (`gh issue create`, title `[P#] … (F3|F4)`); append 5 lines to docs/HANDOFF.md. Never keep notes elsewhere."
4. Move this log to `docs/audit/decision-log-F0-F2.md` and reference it from AGENTS.md.
Do not put lists of bugs into AGENTS.md or CLAUDE.md — they are loaded into every session and go stale.

---

## Appendix A — text for AGENTS.md

```markdown
## Reporting (one place, same format — every agent)
- Known problems live ONLY in GitHub issues: title `[P1|P2|P3|P4] <what> (F3|F4)`, body = where (file:line),
  why it matters, suggested fix. Never in ad-hoc markdown files, code comments without an issue, or chat only.
- Every PR uses .github/pull_request_template.md; sections "Deviations", "Not done", "Risks", "Needs a human"
  are mandatory (write "none"). Each "Not done" item is created as an issue before the PR is opened.
- Code TODOs only as `TODO(#<issue>)`. Skipped tests only with `reason="#<issue>"`.
- End of session: 5 lines in docs/HANDOFF.md (branch, done, next, risks, issue numbers).
- Approved decisions that must not be reverted: docs/audit/decision-log-F0-F2.md (section 3).

## Cross-cutting rules (learned in F0–F2)
- Demo mode = `STAFETA_DEMO_MODE=1` only. Who acts = `backend/app/security.current_actor` only (X-Demo-Role in
  demo mode → seeded Practitioner; otherwise 401). Never add another auth switch or actor helper.
- Contract changes additive only; run `make contract`; generated files (openapi.json, schema.d.ts, lockfiles)
  are never hand-merged — take main, regenerate. After a backend merge the frontend runs `pnpm gen:api`.
- ADR files are named `docs/adr/XXXX-<slug>.md` until merge; the merge captain assigns the number.
- Shared IRIS (ACI): never run `-m iris` tests or `seed --reset` against it; only the merge captain resets,
  then reindexes vectors. All writes idempotent; test data tagged `stafeta-test`.
- Frontend never decides as-of; it renders `excluded_documents` / flags from the API. Unknown counts are `null`.
- After a rebase the human pushes with `--force-with-lease`; agents never force-push.
```

## Appendix B — `.github/pull_request_template.md`

```markdown
## What
<!-- 2–4 lines; Closes #… -->

## How verified
<!-- commands + result (make check, make eval numbers, screenshots for UI) -->

## Contract changes
<!-- none | additive: endpoints/fields + note for P3 -->

## Deviations from the prompt / decisions
<!-- none | list with reason -->

## Not done (each → issue #)
<!-- none | - [ ] … (#123) -->

## Risks
<!-- none | … -->

## Needs a human
<!-- none | e.g. run STAFETA_LLM_CACHE=0 make eval, reseed ACI, clinical decision -->
```

Owners: **P1** architect/IRIS/FHIR/infra/vector search · **P2** extraction, handover, consistency ·
**P3** frontend · **P4** domain/workflow, API (`api`, `security`, `outputs`, `notify`), E2E, demo script, pitch.

---

## 1. Environment & process facts

- IRIS for Health Community on ACI `rg-team73 / aci-irishealth-team73`, **IP 57.174.97.175**, no DNS label →
  IP can change on restart. Storage is NOT persistent: after a restart run `make iris-bootstrap`, seed, reindex.
  Do not stop it overnight; delete after submission. Ports public over HTTP → fictitious data only.
- Bootstrap done: FHIRSERVER namespace, `/fhir/r4` (metadata HTTP 200), `Stafeta.DocChunk` + HNSW index.
- `.env` is shared privately between humans; agents must not read/edit it (hook). `.env.example` IS editable.
- `make up` = backend + mailpit against IRIS from `.env` (ACI). `make up-local` = adds local IRIS via
  `docker-compose.local-iris.yml` (override sets IRIS_HOST=iris). Backend and mailpit bound to **127.0.0.1** only.
- APIM: model `gpt-6-1-sol-dz-eu` (= `LLM_MODEL_EXTRACT`). **No embedding deployment exists** (all 404).
- Branch ruleset on `main`: PR required (1 approval, squash only), status checks `backend` + `frontend`,
  linear history, block force push/deletion, Copilot auto-review; bypass = repo admin "for pull requests only".
  Repo: squash only, auto-merge on, auto-delete head branches. Copilot cloud agent: workflows allowed.
- Each person: own git identity (`user.name`, GitHub noreply e-mail) — P3 and P4 initially had none.
- Playwright on each WSL machine: `sudo npx playwright install-deps chromium && npx playwright install chromium`,
  then approve the `playwright` MCP server from `.mcp.json` at `claude` start (`/mcp` to check).

---

## 2. Cross-cutting conventions (drifted — audit these first)

| # | Convention | Why |
| --- | --- | --- |
| X1 | **One demo-mode env var: `STAFETA_DEMO_MODE`.** F2-4 introduced `STAFETA_DEMO_AUTH`, F2-1 used `STAFETA_ENV` → unify. | Two switches = auth bypass confusion |
| X2 | **One `backend/app/security` `current_actor` dependency** used by every endpoint (F2-1 transitions, F2-2 confirm, F2-4 tasks, MDT conclusion). `X-Demo-Role` honoured only if `STAFETA_DEMO_MODE=1`, validated against the Role enum, mapped to a **seeded Practitioner/PractitionerRole** (gives real ids for `confirmed_by`, `AuditEvent.agent`); missing header in demo mode = coordinator; outside demo mode → **401** (fail closed, no SYSTEM fallback). CORS allows `X-Demo-Role`. Production path (OAuth2/OIDC + SMART scopes) documented in `docs/security-privacy.md`, refs issue #4. | Several parallel implementations appeared |
| X3 | **ADR numbering:** several PRs created ADR-0004 (handover contract, referral intake, coordination). Rule: until merge name files `docs/adr/XXXX-<slug>.md`; merge captain assigns the next free number; one format (check existing). | Clashes |
| X4 | **Contracts:** changes additive only; every backend PR runs `make contract`; `contracts/openapi.json`, `frontend/src/lib/api/schema.d.ts`, `uv.lock`, `pnpm-lock.yaml` are never hand-merged — take `main`, regenerate. After each backend merge P3 runs `pnpm gen:api` and commits `schema.d.ts`. | Generated-file conflicts |
| X5 | **Shared ACI rules:** only the merge captain (P1) runs `seed --reset`, announced in chat; after any reset → **reindex vectors** (new DocumentReference ids orphan old `DocChunk` rows). All writes idempotent (conditional create/update by identifier). Test data tagged `stafeta-test`, never on the demo patient. | One shared IRIS |
| X6 | **Integration tests (`-m iris`) only against local IRIS.** Add guard in `backend/tests/conftest.py`: skip unless IRIS_HOST ∈ {localhost, 127.0.0.1, iris} or `STAFETA_ALLOW_SHARED_IRIS_TESTS=1`. (F2-4 accidentally hit ACI by running a test by path.) | Prevents polluting demo data |
| X7 | `docs/HANDOFF.md` is append-only → root `.gitattributes`: `docs/HANDOFF.md merge=union` (was requested in fe/shell — verify). | Rebase conflicts |
| X8 | Unknown counts are **`null`, not `0`** (UI shows "—"). A false "0 chybí" is worse than a dash. | Clinical UI honesty |
| X9 | Frontend never decides as-of; it renders `excluded_documents` / per-document flags from the API. | Single source of truth for non-negotiable #4 |
| X10 | After a rebase, the **human** pushes `git push --force-with-lease origin <own branch>` (agents are denied force push). Worktree branches (`worktree-*`) renamed to `<area>/<desc>` before PR. | Ruleset + hooks |
| X11 | Copilot cloud agent has no `.env` / IRIS access: only `pytest -m "not iris"`, FHIR mocked via respx, fake embedder. | Cloud agent sandbox |
| X12 | PRs > 400 lines accepted when commits are layered; review with a focused risk checklist instead of line-by-line. | Time |

---

## 3. Approved decisions per area (do NOT revert)

### F1-1 Foundation (P1) — merged
- Seed has **two scenarios**: default `story` = directory, users, patient, 13 DocumentReferences with simulated
  received times, case Task.businessStatus `pripraveno_mdt` (snapshot as of 2026-10-21T08:00+02:00), no step Tasks;
  `--scenario demo-start` (used by `make demo-reset`) = directory, users, patient only — **no case, no documents**
  (GP creates the case live in demo step 1; documents uploaded in step 3). Makefile + demo-flow skill updated. *Verify.*
- `--reset` deletes only `meta.tag=stafeta-demo` resources and **keeps AuditEvents** (non-negotiable #6).
- RČ identifier system **`https://ncez.mzcr.cz/fhir/sid/rcis`** (CZ Core cz-rodcis-identifier), value from the documents.
- Known risks accepted for PoC: write + AuditEvent not atomic; no auth until #4; access log path nit.
- Issues that should exist: `[P4] Scope uploaded document ids per patient`, `[P1] Minimise RČ in RelatedPerson
  and Coverage identifiers`, `[P1] Audit failed reads`, `[P1] Atomic write + AuditEvent via FHIR transaction bundle`,
  plus TODO issues for state machine / mock login (#4).

### F1-2 Frontend shell (P3) — merged
- Temporary view-model types in `src/lib/domain.ts`; MSW pinned to v2; screenshots via script.
- **Bug to verify fixed:** GP "Potvrdit přijetí" was shown only from simulated date 22. 10. → must be **state-driven**
  (MDT conclusion sent to GP and not yet acknowledged: case `zpetna_vazba_odeslana` / Communication without read
  receipt). Demo step 6 runs on **21. 10.**
- Mock-only copy (epikríza draft, finding wording) marked `// MOCK copy – replaced by API in F2/F3`.
- No Chromium libs / scratch folders tracked in git.

### F1-3 Extraction (P2) — merged
- Results: **first run recall 94.4 %**, tuned **52/54**, evidence validity **100 %**, **0 post-MDT facts**.
  Tuned on the same 13 documents (no holdout) → pitch must say so.
- Fact type `recommendation_or_plan` renamed **`documented_plan`** (must not read as AI advice).
- Quote repair only for sub/superscript differences (CHA2DS2 vs CHA₂DS₂), only on a unique match, counted in the
  report, and the **stored quote is the source text**.
- Backend path calls **`doc_included(require_received=True)`** (raw files have no received date).
- LLM cache keyed by sha256(model + prompt + text); any prompt/normalisation change invalidates it →
  `STAFETA_LLM_CACHE=1 make eval` must reproduce the numbers before a cache commit.
- Optional `Fact.specimen` field (sérum/moč) added now, filled by prompt v2. *Verify.*
- **Prompt v2 (planned, P2, after F2-2 + C1/C2, timebox 45 min, PR `ai/extraction-prompt-v2`, keep only if eval
  not worse):** negated value = verbatim sentence; lab rows get specimen; fix "Zátěž toleruje dobře" classified as
  symptom, the 2019 episode in the wrong field, "pracovní neschopnost" not extracted.

### F1-4 Domain & workflow (P4) — merged
Approved deviations:
- Histology task due **19. 10.**; separate `sla_due` **15. 10.** drives escalation on **16. 10.**
- Queue buckets: **Nový = only `odeslano`**; `triage` and later = Aktivní; Odložený = flag `odlozeny`.
- Task `accept` requires prior **`order_confirmed` with place AND date** ("odeslaná žádanka ≠ objednané vyšetření").
- Event **`gp_opened`** (audited read receipt).
- **`record_mdt_conclusion` requires `confirmed_by`** (clinician id).
- `events.py` added. Move rules: no overwrite of P1's `__init__.py`, P1 models imported (no duplicate enums),
  `contracts/case-states.md` + ADR updated, tests in `backend/tests/domain`.

### F2-1 Referral & triage (P4)
- Endpoint is **`/api/referrals/prefill`** (UI used `/referrals/parse` → switch).
- Must hold before/at merge: integration test run on **local** IRIS (If-Match inside transaction and `urn:uuid`
  resolution unverified — fallback: conditional create `ifNoneExist` on RČ); single `current_actor` (X2);
  **upload size checked before parsing** (Content-Length + streamed cap → 413 problem+json in Czech);
  **prefill audited** (AuditEvent subtype extract, no patient ref, no PHI in logs); duplicate open case → 409 with
  neutral Czech message without case id or other KOC names.
- Case summary extended (additive): `postponed`, `suspected_diagnosis` (code + text + evidence), `koc`,
  `referring_gp`, `counts {missing, conflict, stale}` = **null** until the handover service provides them.
- Issues: `[P4] Sync EpisodeOfCare.status with case state (F3-4)`, `[P4] Filter GET /api/cases by participant (#4)`.
- Deps `python-multipart`, `pypdf` added via `uv add`.
- Demo consequence: step 1 can be repeated only after `make demo-reset` (409 on duplicate).

### F2-2 Handover (P2) — PR #14 `ai/handover-assembly`, PR 2 `ai/handover-persistence` stacked
- Negation lock repair **only if certainty = negated AND the quote itself contains a negation cue**; value becomes the
  exact source quote; counted.
- **No findings stub in eval** (eval must never consume golden-derived findings). Standalone gate **13/15**, issue
  "Raise field-status gate to 14/15 when C1/C2 rules land". `assemble_handover(..., findings=None)` parameter so F3-1
  plugs in without touching assembly.
- Contract (additive, Role enum from domain): `missing_items[{item, reason, suggested_owner}]`,
  `review{state: draft|confirmed|accepted_missing, by (Practitioner id), at (ISO tz)}` (accepted_missing needs reason),
  Handover `status preliminary|final`, `composition_id`, **per-value `items[] = {label?, value, unit?, clinical_date?,
  evidence[{doc_id, quote, authored_at, received_at}]}`** — the per-value evidence is the core pitch claim. *Verify it
  exists; if not → P0.*
- Real epicrisis requires P2 to run `STAFETA_LLM_CACHE=0 make eval` (agents cannot read .env), then verify offline
  and commit the cache. Epicrisis: every sentence cited, IDs exist, fallback to cited bullets.
- PR 2 scope: Composition/Provenance mapping, **idempotent** persist, `POST …/handover/sections/{n}/confirm` via
  `current_actor`, Composition `final` when all sections confirmed or accepted_missing. After #14 squash-merge:
  `git rebase --onto origin/main <#14 branch> ai/handover-persistence`.
- **C1/C2 rules** (R1 drug pause vs procedure date, R2 specimen date vs report/procedure date) as small PR
  `ai/consistency-c1-c2` in a parallel worktree, wired via `findings=`. Demo step 3 needs "Nesouhlasí" for both.

### F2-3 UI wiring (P3) — split `fe/wiring-steps-1-2`, `fe/wiring-steps-3-4`
- MSW handlers use the exact endpoint paths from prompts F2-1/F2-2/F2-4; `features/handover/api.ts` switches from its
  own mock shape to generated types; MSW fixtures typed from the same schema.
- Fix now: no as-of logic in UI (X9), "po MDT – nezahrnuto" badge from API data; consent rows read-only with source
  chip; triage hint ("výsledky 01–06 nejsou přiloženy") with evidence chip quoting report 07; per-value evidence chips
  once `items[]` exist; "Potvrdit objednání" asks for place + date; MDT conclusion only in role Lékař KOC.
- Deferred (one issue, F4): per-section edit error flag; showing the referral note.
- Screenshots may be manual (Win+Shift+S) until Playwright works.

### F2-4 Coordination (owner P4; built by an agent)
- API verbs `confirm | perform | deliver_result | fail | cancel` chained internally onto machine events:
  confirm = order_confirmed(place, scheduled_at) + accept (**place AND date required → 422**);
  perform = start + performed (dependency guard applies); deliver_result = result_delivered (optional document_id).
  Chains are **all-or-nothing** (validate all guards, persist once, 409 names the blocking guard);
  **one AuditEvent per machine event**, shared correlation id.
- PlanDefinition owner roles: CT (KOC 1 radiology), odběry + TM (laboratoř), histologie (patologie) →
  `external_workplace`; EUS-FNB, algeziologie, psychoonkologie, MDT → `koc_physician`; coordinator orders/confirms.
  Coordinator may record performed/result_delivered **on behalf of** `external_workplace` tasks only
  (AuditEvent agent = coordinator, onBehalfOf = workplace Organization); document upload does the same.
  Board lane = concrete owner, else owner_role.
- **Clinical decision:** launching the pathway requires **`indicated_by` = a KOC physician** → stored as
  `CarePlan.author` + `ServiceRequest.requester` + Provenance (agent coordinator, onBehalfOf physician); missing →
  422 "Sada vyšetření vyžaduje indikujícího lékaře KOC."; UI pre-fills the case physician. Record in the ADR.
- Action id renamed `eus_fnb` → **`eus-fnb`** (FHIR ids forbid `_`) → check P4 domain tests and P3 mocks.
- `.env.example`: `STAFETA_DEMO_MODE`, `STAFETA_WATCHDOG_ENABLED`, `STAFETA_WATCHDOG_INTERVAL_S` (drop `STAFETA_DEMO_AUTH`).
- After F2-1 + F2-4 merge: P1 reseeds ACI (announce) and reindexes vectors.
- Open (issues for P4, F3): **demo time helper** `POST /api/demo/advance?to=2026-10-16` (demo mode only) that replays
  story events so CT/EUS/labs are done before the histology escalation; **baton holder from one function** for case
  summary, inbox and board (inconsistency would be visible on stage); per-case authorisation (documented).

### F2-5 Vector search (P1)
- Chunks **~450 chars / 80 overlap, k=8** (MiniLM embeds only first 128 tokens); sizes are settings.
- Each chunk prefixed with a context header, e.g. `[09 Biopsie výkon KOC2 · 2026-10-12] `, excluded from quote checks.
- Embeddings: local fastembed `paraphrase-multilingual-MiniLM-L12-v2`, 384 dims, default; APIM provider behind the
  same interface (`dimensions=384`) only if `EMBEDDING_MODEL` is set. Fake deterministic embedder in unit tests/CI.
  Store model name + dims with the index; refuse search on mismatch; `make reindex`. Model baked into the backend
  Docker image (pinned revision).
- `/ask`: answers only from retrieved chunks, every sentence cited; advice questions → "Aplikace nedoporučuje léčbu;
  v dokumentaci je uvedeno:" + cited statements; "V dokumentaci k <datum> není uvedeno." when absent.
- `docs/vector-search.md` with latency with and without HNSW (for InterSystems judges).

---

## 4. Demo-critical checklist (G2 = steps 1–4 end to end; verify on `main` after fixes)
1. `make demo-reset` → no case; GP uploads `07_PL_zadost_KOC2` → prefill with evidence (Alena Procházková, 63 let,
   ZP 211, C25.0 suspektní, dcera + telefon, consent sentence) → Odeslat → state **Odesláno**, bucket Nový,
   baton "Koordinátor KOC 2".
2. Coordinator Převzít → triage proposes 01, 02, 03, 05, 06 with workplaces; hint cites report 07; one click request.
3. Upload 01–06, 08–11 → handover: 15 sections, per-value chips, **Chybí** ECOG/TNM/e-mail (with owner),
   **Nesouhlasí** apixaban dates + histology sample date (C1/C2), **Zastaralé** weight, physician confirms sections.
4. Launch "Karcinom pankreatu – diagnostika" (with indicating physician) → board lanes populated, baton holder,
   histology escalation on 16. 10. (needs demo time helper).
Also: `STAFETA_LLM_CACHE=1` everywhere in the demo; reports 12–13 excluded as of 21. 10.

## 5. Order of work for P2 (agreed)
#14 merge → PR 2 persistence ∥ C1/C2 (two worktrees) → prompt v2 → rest of F3-1.

## 6. Pitch notes collected
- Numbers: "Na 13 dokumentech demo pacientky: první běh recall 94 %, po ladění 52/54; každá hodnota má doslovnou
  citaci (100 %); nic po MDT se do podkladů nedostane." Say it was tuned on these 13 documents.
- Safety is mechanisms, not a metric: value without verbatim quote is dropped; negation/suspicion rules
  ("AI nesmí z podezření udělat diagnózu – máme na to test"); draft until a physician confirms; everything audited.
- "Aplikace nedovolí objednat invazivní výkon bez indikujícího lékaře." · "Odeslaná žádanka ≠ objednané vyšetření."
- RČ on the CZ Core identifier system; FHIR R4 on IRIS for Health; vector search in IRIS with latency numbers.