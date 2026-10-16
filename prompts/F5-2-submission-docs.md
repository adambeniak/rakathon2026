<!-- WHO: P1 or P2 · TOOL: Claude Code Sonnet 5.5 (or Copilot GPT-6 Luna for formatting) · MODE: normal · WHEN: F5 (11:30–13:00) -->

You are the technical writer preparing the submission package. Code is frozen: only docs and README may change.

1. README.md (Czech first, English summary): what Štafeta is (3 sentences), screenshot, how to run in 5 minutes
   (`make up && make iris-bootstrap && make seed`, `pnpm dev`), demo credentials/roles, architecture image, the
   standards used, AI safety design, eval results table (from eval/report.json with commit hash), limitations
   (fictitious data, simulated eŽádanka/MHD, cached LLM in demo), license and third-party components
   (incl. the MIT kit skills), team.
2. docs/architecture.md: update to what actually shipped; mark stretch items not done.
3. docs/fhir-mapping.md: final table + example instances in docs/examples/*.json (validated).
4. docs/security-privacy.md: role/purpose/permission matrix, data flows, DPIA outline, MDR/AI Act position,
   production hardening list.
5. docs/roadmap.md: 90-day pilot plan and the post-hackathon issues (label `post-hackathon`).
6. Check: no secrets (`git grep -nE "api-key|APIM_API_KEY=.+|IRIS_PASSWORD=.+"`), no real data, links work.
Finish with the list of files changed and a 5-line summary we can paste into the submission form.
