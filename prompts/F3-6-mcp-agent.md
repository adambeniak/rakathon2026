<!-- WHO: P1 or P2 · TOOL: Claude Code Sonnet 5.5 · MODE: normal · WHEN: F3, STRETCH — timebox 90 min -->

ROLE: Engineer exposing the shared case to AI agents safely (our "agentic AI component" for the InterSystems judges).

CONTEXT: Kit examples in `.claude/skills/kit-iris-vector-search` and the FHIR-AI-Hackathon-Kit `mcp-examples`
(FastMCP). Backend services for handover, findings, tasks, ask-the-case exist.

GOAL: An MCP server `stafeta-mcp` (FastMCP, streamable HTTP, read-mostly) so that any MCP client (Claude Desktop,
Copilot agent mode) can act as an "MDT preparation assistant" for a coordinator — with the same role checks and audit.

TOOLS (all take case_id and as_of; all calls write AuditEvent with agent = "mcp-client")
- `get_case_summary` — state, baton holder, deadlines, counts
- `get_handover` — 15 fields with status + evidence
- `list_findings` — open findings with evidence
- `search_documents` — IRIS vector search over chunks (top k with quotes)
- `draft_document_request` — returns a DRAFT request text for a missing item (never sends)
- `propose_tasks_from_findings` — returns DRAFT tasks (never creates)
No tool may send messages or change state; humans do that in the app.

ALSO: a 60-second demo script — in Claude Desktop: "Připrav mi podklady k MDT 21. 10. pro pacientku Procházkovou a
řekni, co chybí" → the agent calls the tools and answers with citations.

ACCEPTANCE
- [ ] `cd backend && uv run python -m app.mcp_server` starts; tools listed in an MCP inspector; demo prompt works end to end
- [ ] Auth: a static demo token per role; documented production path (OAuth, SMART scopes) in docs/security-privacy.md
- [ ] PR `iris/mcp-agent`
