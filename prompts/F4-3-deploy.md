<!-- WHO: P1 · TOOL: Claude Code Opus 5.5 · MODE: PLAN · WHEN: F4 (08:00–10:30). Decide by 09:00: cloud deploy or "laptop + ACI IRIS". -->

ROLE: Cloud engineer (Azure) shipping a safe, cheap demo deployment.

CONTEXT: Resource group rg-team73 (Contributor). IRIS runs in ACI (public HTTP — fictitious data only). Microsoft guide:
Static Web Apps for the frontend, Container Apps (consumption, min replicas 0, max 1) for the backend; API keys only on
the backend; clean up after the event. Read README, .env.example, docs/security-privacy.md.

GOAL: A reachable demo URL with the full flow, or — if risky — a documented decision to demo from a laptop against the
ACI IRIS, plus the production architecture written down for the pitch.

PLAN FIRST
Compare in a table: (A) SWA + Container Apps + ACI IRIS, (B) laptop + ACI IRIS, (C) everything local. Criteria: time to
working (min), failure modes on stage, cost, what we can claim in the pitch. Recommend one and wait for approval.

BUILD (if A)
1. Backend image (multi-stage, non-root, healthcheck) → ACR or GHCR; Container App with secrets (APIM key, IRIS password)
   from Container Apps secrets (Key Vault reference if time allows), env from .env.example, ingress HTTPS only.
2. Frontend on Static Web Apps (build-time API base URL), CORS on the backend restricted to the SWA origin.
3. `scripts/deploy_azure.sh` idempotent; `scripts/teardown_azure.sh` deletes only what we created (never the RG).
4. Smoke: run `@smoke` E2E against the URL.
5. `docs/deployment.md`: what runs where today, and the production target (provider-hosted, private networking, TLS,
   licensed IRIS for Health or HealthShare, Entra ID / national identity, Key Vault, backups, monitoring, EU region).

ACCEPTANCE
- [ ] Demo URL works end to end with cached LLM, or decision B/C documented with reasons
- [ ] No secret in images, logs or repo; teardown script tested on a dry run
