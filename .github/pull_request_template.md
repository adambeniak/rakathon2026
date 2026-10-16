## What
<!-- 2–4 lines: what and why. Closes #… -->

## Area / owner
- [ ] be  - [ ] ai  - [ ] fe  - [ ] wf  - [ ] iris  - [ ] qa  - [ ] infra  - [ ] docs

## How verified
<!-- commands + result: `make check` summary; for extraction/consistency `make eval` numbers; for UI a screenshot -->

## Contract changes
<!-- none | additive: endpoints/fields + note for P3 (`make contract` run, `pnpm gen:api` needed) -->

## Deviations from the prompt / decisions
<!-- none | list with reason (see docs/audit/decision-log-F0-F2.md §3 and docs/audit/TRIAGE.md §Keep) -->

## Not done (each → issue #)
<!-- none | - [ ] … (#123) — create the issue BEFORE opening this PR -->

## Risks
<!-- none | … -->

## Needs a human
<!-- none | e.g. run STAFETA_LLM_CACHE=0 make eval, reseed ACI, run -m iris on local IRIS, clinical decision -->

## Checklist
- [ ] Small and focused (aim < 400 changed lines excl. generated files)
- [ ] No secrets, no real personal data, no PHI in logs
- [ ] `contracts/` unchanged — or changed additively with an ADR and the owner's approval
- [ ] AI output carries evidence; no clinical advice in generated text (clinical-safety-reviewer run if relevant)
- [ ] Docs updated (`docs/fhir-mapping.md`, `docs/HANDOFF.md`) if behaviour changed
- [ ] Known problems filed as issues (no new notes files, TODOs only as `TODO(#n)`)
- [ ] Written/assisted by: <!-- human / Claude Code / Copilot (model) -->
