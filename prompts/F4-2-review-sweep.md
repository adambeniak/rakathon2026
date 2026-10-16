<!-- WHO: P1 (coordinates), fixes by owners · TOOL: Claude Code (Opus for orchestration) · MODE: normal · WHEN: F4 (08:00–09:30) -->

You are the release manager for a hackathon demo in 4 hours. Run an independent review sweep of `main` using our
subagents IN PARALLEL (they do not edit code), then produce a triaged fix list.

1. Launch in parallel:
   - `extraction-auditor`: run `make eval`, audit the handover for as_of 2026-10-21 against the golden set.
   - `clinical-safety-reviewer`: review all LLM prompts (`backend/app/extraction/prompts*`, `consistency`, `ask`),
     all generated texts shown in UI, MDT record template, e-mail and GP/reviewer views.
   - `security-privacy-reviewer`: review backend API authz, logging, uploads, CORS, secrets, docker/azure config.
   - `fhir-architect`: validate one example of every resource type we write (POST to `$validate` where possible) and
     check `docs/fhir-mapping.md` matches the code.
   - `ux-reviewer`: walk the 6 demo steps at 1440×900.
2. Merge their outputs into ONE table: severity · area · finding · owner (P1–P4 by CODEOWNERS) · fix estimate (min).
3. Rules for the freeze: only fix critical/high items and anything visible in the demo; everything else becomes an
   issue labelled `post-hackathon` and goes to the roadmap slide.
4. Create the issues with `gh issue create` (ask me before running), assign owners, and print the fix list.
