<!-- WHO: P1 · TOOL: Claude Code (any model) · MODE: normal · WHEN: F0, right after copying the starter kit -->

You are the platform engineer of a 4-person hackathon team. The repo was just initialised from a starter kit
(read AGENTS.md and CLAUDE.md first). Do NOT build features. Your only goal is to prove the environment works and
report blockers in under 20 minutes.

Do this, in order, and stop at the first hard blocker:
1. Check tool versions: git, docker, docker compose, uv, python 3.12, node 22, pnpm, az CLI, gh CLI, claude.
   Print a table: tool · version · OK/missing. For missing tools print the one-line install command for macOS,
   Linux and Windows (WSL).
2. Verify `.env` exists (do not read its contents — it is denied to you). If it is missing, tell me to run
   `cp .env.example .env` and which variables I must fill.
3. Ask me to run these myself and paste the output (you must not see secrets):
   - APIM smoke test: `set -a; . ./.env; set +a; curl -s "$APIM_BASE_URL/chat/completions" -H "api-key: $APIM_API_KEY" -H "Content-Type: application/json" -d '{"model":"'$LLM_MODEL_EXTRACT'","messages":[{"role":"user","content":"Odpověz jedním slovem: funguje?"}]}' | head -c 400`
   - IRIS: `make aci-status` (shared ACI) or `make up` (local), then `make iris-bootstrap`.
4. From the outputs, decide and write to `docs/HANDOFF.md`: APIM OK? which model ids work? IRIS version
   (`$zv` printed by bootstrap)? HNSW index created or fallback? FHIR metadata HTTP 200?
5. Make the hooks executable (`chmod +x .claude/hooks/*.sh scripts/*.sh`) and commit the starter kit DIRECTLY to `main`
   with message `chore: initialise repo from starter kit` (before the branch ruleset is enabled — README step 4).
6. ACI check: run `az container logs -g rg-team73 -n aci-irishealth-team73 | tail -40` (ask me to run it) and look for
   errors about the password file (IRIS renames/deletes it, the ACI secret mount is read-only). Report what you see.

Output: the version table, the decisions from step 4, and a list of blockers with owner suggestions.
