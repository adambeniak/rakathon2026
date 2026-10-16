<!-- WHO: P3 · TOOL: Claude Code Sonnet 5.5 + frontend-design skill, or Copilot GPT-6.1 Sol in VS Code · MODE: normal · WHEN: F2 (20:00–24:00) -->

ROLE: Senior frontend engineer and UX designer for clinical tools.

CONTEXT: The shell with mocks is merged (F1-2). Backend endpoints for referral, cases, transitions, document requests
and handover exist or are in review (F2-1, F2-2). Regenerate the client with `pnpm gen:api` after each contract change.
Read .claude/rules/frontend.md and the demo-flow skill.

GOAL: Demo steps 1–4 run in the browser against the real API (MSW stays for tests and offline work).

BUILD
1. Referral (`/referral/new`, role PL): drop zone → calls prefill → shows a compact summary card with evidence chips and
   2 decisions only (KOC from directory, consent checkbox) → "Odeslat do KOC". Then a confirmation with the case state
   and "co bude dál". No form fields except optional note.
2. Inbox (`/inbox`, role koordinátor): 3 columns Nový / Aktivní / Odložený, cards show patient, state badge, baton holder,
   next deadline (red when overdue), counts Chybí/Nesouhlasí. Sorting by deadline. Click → case.
3. Case detail header: state, "Na tahu: <role/person> do <datum>", T1/T2/T3 placeholders, primary action depending on
   state (Převzít / Vyžádat podklady / Připravit MDT / Odeslat závěr).
4. Triage panel: proposed document requests (from API) as a checklist with recipient → "Vyžádat vybrané" (one click).
   Received documents appear in Dokumenty with authored and received date.
5. Handover review (`/cases/:id/handover`): 15 sections in the order of Handover_obsah; each section shows status pill,
   values, `<EvidenceChip>` per value (popover: document, date, highlighted quote, "Otevřít dokument" side panel),
   buttons "Potvrdit sekci", "Upravit" (inline edit with reason), "Kopírovat". Sticky summary bar: X potvrzeno,
   Y chybí, Z nesouhlasí, "Návrh AI – čeká na potvrzení lékařem" label until all confirmed.
6. Coordination (demo step 4, needs F2-4): "Úkoly" tab with the button "Spustit sadu: Karcinom pankreatu – diagnostika",
   the board "Kdo je na tahu" (lanes PL · Koordinátor · Lékař KOC · Externí pracoviště · Pacient) with state, place,
   due date, overdue badge and blocking dependencies; task actions (Potvrdit objednání / Provedeno / Výsledek doručen).
7. Loading, empty and error states in Czech; optimistic updates only for confirmations.

ACCEPTANCE
- [ ] Steps 1–4 of the demo work end to end locally (`make up`, `make iris-bootstrap`, `make seed`, `pnpm dev`)
- [ ] Run the `ux-reviewer` subagent on inbox, case detail and handover; fix its top 3 issues
- [ ] `pnpm lint && pnpm typecheck && pnpm test` green; screenshots in PR `fe/wiring-steps-1-4`
