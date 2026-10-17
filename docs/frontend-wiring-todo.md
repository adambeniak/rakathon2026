# Frontend wiring: what is still on mocks (as of rebase onto main 696dfa7)

Real now (generated client, `frontend/src/features/cases/adapter.ts`): `GET /api/cases`, `GET /api/cases/{id}`
(queue bucket, postponed flag, counts, KOC, referring GP are taken from the API) and the handover
(`GET .../handover`, `POST .../sections/{number}/confirm`; wire `as_of`/`fields`/`excluded_documents[].doc_id` adapted in `features/handover/adapter.ts`).

The contract now has the endpoints below, but the screens still call the provisional MSW paths from the first
iteration (they work with `VITE_MOCKS=1` only). Not blocking this PR; each row is one small follow-up:

| Screen / hook | Still calls (mock) | Contract endpoint | Notes |
| --- | --- | --- | --- |
| KOC directory (`referral/api.ts`) | `GET /api/koc` | `GET /api/directory/kocs` | `KocEntry[]` |
| Referral prefill | `POST /api/referrals/prefill` `{filename}` | `POST /api/referrals/prefill` → `ReferralPrefill` | request is not JSON-with-filename; check the schema (file upload) |
| Referral submit | `POST /api/referrals` | `POST /api/referrals` → `ReferralCreated` | no `body` in the contract's JSON schema, verify (multipart?) |
| Claim / state changes | `POST /api/cases/{id}/claim` | `POST /api/cases/{id}/transitions` → `CaseSummary` | event names in `contracts/case-states.md` (`accept`, ...) |
| Triage checklist | `GET/POST /api/cases/{id}/document-requests` | `GET .../document-requests/proposals` (`ProposalsOut`, with `evidence`) + `POST .../document-requests` | proposals carry the evidence for the hint chip |
| Task set | `POST /api/cases/{id}/task-sets` | `POST /api/cases/{id}/pathways` (`LaunchPathwayRequest`) | |
| Task board | `GET /api/cases/{id}/tasks` + `.../tasks/{t}/phase` | `GET /api/cases/{id}/board` (`Board`), `POST /api/tasks/{task_id}/transitions` | board already groups by baton holder; check lanes vs `Board` |
| Handover | `GET /api/cases/{id}/handover` and `POST .../sections/{number}/confirm` are **on the contract** (`features/handover/adapter.ts`, `expected_value_hash`); still mock: `.../confirm-all`, `.../edit` | no edit / confirm-all endpoint in the contract | per-row edit attribution (`items[].edit`) is a mock-only extension: the API records only `review.edited/by/at` and no reason; the real backend therefore shows no per-row reason |
| Findings, MDT, `gp/cases`, `reviewer/cases` | mocks | not in contract | `GET /api/cases/{id}/alerts` may replace findings |

## Known gaps / small issues (not fixed here)

- `diagnosis` is not shown: `CaseDetail.suspected_diagnosis` is AI-derived and must render with an `EvidenceChip`
  (it carries `evidence`); header and inbox card need a chip-capable slot first.
- Header T1/T2/T3 clocks stay placeholders (no field in `CaseDetail`).
- `Mdt.tsx` uses a UI constant as the default `as_of` of its date picker; it should come from the API.
- Per-section edit error flag (one `editError` for all sections), referral note not stored/shown by the mock.
- Per-value evidence chips: the adapter already carries `items[].evidence` into `rows[].evidence`, but only read-only consent rows render it; show one chip per value for all rows.
- No browser available to the `ux-reviewer` agent (Chromium not installed): no screenshots yet, add them by hand to
  the PR (`npx playwright install chrome`, then `VITE_MOCKS=1 pnpm dev`).
