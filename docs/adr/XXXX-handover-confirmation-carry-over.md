# ADR-XXXX: Handover snapshots carry over the physician's decisions on unchanged sections; the MDT screen stores the mdt_start snapshot

- Date: 2026-10-17 · Status: proposed · Owner: P2 (files in P1/P3 areas, approved by the session owner) · Issue: #122
- The number is assigned by the merge captain; until then the file is named `XXXX-<slug>.md`.

## Context
- A handover is one `Composition` per (case, as_of) (ADR-0004, identifier `sid/handover|<case>@<as_of UTC>`), and the
  section reviews live on it. The as-of rule makes the key necessary: another cut-off can include other documents.
- Demo step 3 runs before the pathway launch, so the cut-off is the demo clock. Step 5 runs after it, so the cut-off
  is `mdt_start`. That gives two Compositions, and the sections the physician confirmed in step 3 showed
  'Návrh AI – čeká na potvrzení' again in step 5.
- `GET /handover` never writes. Only a section confirmation stored the Composition, but the readiness gate needs the
  Composition stored at `mdt_start` (ADR mdt-readiness-gate). So `mark_ready_mdt` refused with 'Handover pro MDT ještě
  nebyl sestaven' until the physician had confirmed something in step 5.

## Decision
- **Carry over at persist time, only when the content is identical.** When `HandoverStore.persist` creates a new
  Composition, it searches the patient's Compositions (an audited search) and keeps the handover snapshots of the same
  case (`carried_reviews`, a pure function in `mappers/handover.py`). For each section, the latest physician decision
  across those snapshots counts (confirmed or accepted as missing, by its `at`). It is copied (review and edited value)
  only when its stored `value_hash` equals the newly assembled section's `value_hash`. A section whose content changed
  stays a draft, and an older decision that matched does not outrank a newer one that does not.
- **Who and when stay the physician's.** The copied review keeps the original `by` and `at`. Each copied section gets
  a `Provenance` (activity `provenance-activity|carry-over`) in the same transaction as the new Composition: target =
  the new Composition, agent assembler = the Štafeta Device that copied it (the only agent), entity source = the
  earlier Composition (versioned reference) with `entity.agent` verifier = the physician who decided, extension
  `handover-section`. No new confirmation is invented: the physician is not an agent of the copy.
- If all 15 sections carry over, the new Composition is `final`, attested by the latest decision, as after 15
  confirmations.
- **Trigger: the MDT screen stores the snapshot.** The MDT screen loads its handover with `POST /cases/{id}/handover`
  (idempotent per case and as-of, same response as `GET`) instead of `GET`. Without `as_of` this is `mdt_start`, so
  opening the screen creates the snapshot the readiness gate reads and applies the carry-over. `GET` stays read-only.
- Rejected: keying the Composition by case only (it would break the as-of rule), and overlaying earlier reviews at read
  time (the readiness gate and the MDT record read the stored Composition).

## Consequences
- Step 5 shows the step-3 decisions on unchanged sections, and `mark_ready_mdt` no longer needs a confirmation first.
- A section whose content changed between the snapshots (for example a new report) must be confirmed again. This is the
  same rule as the existing reopen-on-change (`overlay_review`).
- Carry-over runs once, when the new snapshot is created. Decisions made later on another snapshot are not copied into
  a Composition that already exists.
- Opening the MDT screen writes (an idempotent persist, audited). Before the pathway launch there is no `mdt_start`,
  so the snapshot is at the demo clock, the same as a confirmation without `as_of`.
- One extra audited Composition search per new snapshot (all of the patient's Compositions, filtered client-side).
