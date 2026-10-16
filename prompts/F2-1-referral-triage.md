<!-- WHO: P4 · TOOL: Claude Code Sonnet 5.5 (or Copilot GPT-6.1 Sol) · MODE: normal (PLAN if the API shape is unclear) · WHEN: F2 (20:00–24:00) -->

ROLE: Senior backend engineer (FastAPI, FHIR) implementing the entry of the patient journey.

CONTEXT: Foundation (F1-1), domain logic (F1-4) and extraction core (F1-3) are merged. Read AGENTS.md,
docs/fhir-mapping.md, contracts/case-states.md, backend/app/domain/*, .claude/skills/demo-flow (steps 1–2).

GOAL: Demo steps 1–2 work through the API: a GP refers the patient without a long form, the coordinator takes over the
case and requests the missing reports in one click.

BUILD
1. `GET /api/directory/kocs` — KOC list from FHIR Organizations (mCSD-like: name, city, coordinator contact).
2. `POST /api/referrals/prefill` (multipart DOCX/PDF) — normalise + run extraction on the uploaded letter and return a
   prefill: patient identity, contacts, suspected diagnosis, requesting GP, consent statements — each with evidence.
   Nothing is persisted yet.
3. `POST /api/referrals` — GP confirms: target KOC, consent checkbox, optional note. Creates in ONE transaction Bundle:
   Patient (match existing by RČ identifier), RelatedPerson, Coverage, ServiceRequest (urgent), EpisodeOfCare,
   case Task (businessStatus `odeslano`, owner = KOC coordinator role), DocumentReference(s), Consent, AuditEvent.
4. `POST /api/cases/{id}/transitions` — body {event, reason?}; uses the case state machine; persists Task.businessStatus,
   owner, statusReason; writes AuditEvent; returns the new case summary. Forbidden transitions → 409 problem+json.
5. Missing-report detection for triage: from the referral letter facts of type `examination` that are mentioned but not
   attached (report 07 lists 5 examinations "k dispozici na jednotlivých pracovištích"), propose requests with the
   recipient workplace resolved from the directory. `POST /api/cases/{id}/document-requests` creates
   CommunicationRequest + Task (owner = coordinator, due = +2 working days) per item.
6. `POST /api/cases/{id}/documents` — upload received reports; links them to the request and completes its Task
   (businessStatus `vysledek_dorucen`). When all requests are fulfilled, emit event `podklady_kompletni`.
7. Update `contracts/openapi.json` via `make contract` (ask P1 to approve — shared file) and notify P3.

TESTS: unit (mapping, transitions), integration against local IRIS (`@pytest.mark.iris`) for the referral transaction,
API tests with recorded LLM cache.

ACCEPTANCE
- [ ] Upload of `07_PL_zadost_KOC2_2026-10-02.docx` → prefill shows Alena Procházková, 63 let, ZP 211, C25.0 (suspektní),
      dcera + telefon, consent "Souhlasí se sdílením informací s dcerou." — every value with evidence
- [ ] After POST, the case appears in `GET /api/cases` with state Odesláno and baton holder "Koordinátor KOC 2"
- [ ] Triage proposes the 5 reports listed in the letter (01, 02, 03, 05, 06) with correct workplaces; the GP's own
      earlier epicrisis (04, not mentioned in 07) can be added manually as an ad-hoc request
- [ ] `make check` green; PR `wf/referral-triage`
