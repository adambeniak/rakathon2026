# Štafeta — sdílený onkologický případ (Rakathon 2026 · VZP)

Starter kit. Copy the contents into an empty private repo, then follow the steps.

## 1. One-time setup per person (10 min)
```bash
cp .env.example .env                 # fill APIM_* and IRIS_* (never commit; no inline comments after values)
chmod +x .claude/hooks/*.sh scripts/*.sh
# hooks need python3 (or python) on PATH — on Windows use WSL or Git Bash with Python installed
# Claude Code plugins/skills (once per machine)
claude                                # then inside:
/plugin install frontend-design@claude-plugins-official
/plugin marketplace add anthropics/skills   # then /plugin → Discover → install the bundle with webapp-testing
```
P1 only (Opus seat): `/effort xhigh` and `/advisor fable` (needs Fable access; otherwise skip the advisor).
Pro accounts: if `model: opus` in `.claude/agents/*.md` is not available on your plan, change it locally to `sonnet`.

VS Code + Copilot: `.vscode/settings.json` makes Copilot read `AGENTS.md` (not CLAUDE.md, to avoid duplicate rules).
Copilot picks up `.claude/skills/` on its own. Playwright MCP is in `.vscode/mcp.json` and `.mcp.json`.

## 2. Shared IRIS (P1)
```bash
IRIS_PASSWORD='…' bash scripts/aci_up.sh     # team ACI with DNS label stafeta-team73, takes a few minutes
bash scripts/aci_status.sh                    # FQDN → IRIS_HOST and FHIR_BASE_URL in .env (both!)
make iris-bootstrap                           # namespace + FHIR /fhir/r4 + vector table (re-run after every restart)
make seed                                     # idempotent demo case (13 documents); `make demo-reset` = empty start for demo step 1
make up                                       # backend (localhost:8000) + mailpit (localhost:8025) against the IRIS in .env
curl -s localhost:8000/api/health             # {"status":"ok", …}
```
Local alternative (same image): `mkdir -p .iris && echo 'pw' > .iris/password.txt`, put the same value into `.env` as
`IRIS_PASSWORD`, then `make up-local`; for `make iris-bootstrap` / `make seed` point `IRIS_HOST`/`FHIR_BASE_URL` in `.env`
at `localhost`. Local storage is not persistent (like ACI).
Apple Silicon: the pinned digest is amd64 and runs emulated; use the arm64 image variant or the team ACI.

## 3. Work
Prompts per phase are in `prompts/` (header says who, which model, PLAN or normal mode, when).
Rules for every agent: `AGENTS.md`. Claude specifics: `CLAUDE.md`. Subagents: `.claude/agents/`. Skills: `.claude/skills/`
(the `kit-*` skills are from InterSystems' FHIR-AI-Hackathon-Kit, MIT — see `.claude/skills/KIT_SKILLS_LICENSE.txt`).

## 4. GitHub repository settings (P1, 5 min) — AFTER the starter kit is committed to `main`
- Ruleset on `main`: require PR, require status checks (CI backend + frontend), block force pushes, linear history,
  squash merge only, "Automatically request Copilot code review". Allow auto-merge.
- Settings → Copilot → cloud agent: allow workflows to run on Copilot PRs (otherwise click "Approve and run" each time).
- Replace handles in `.github/CODEOWNERS`.

## Data
`data/raw/` — fictitious documents provided for the VZP challenge only; delete after the event per the rules.
`data/golden/` — expected handover and findings for 21. 10. 2026, quotes verified against the documents.
