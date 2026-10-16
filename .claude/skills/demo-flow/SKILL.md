---
name: demo-flow
description: The canonical 6-step Štafeta demo (referral → triage → extraction → coordination → MDT handover → closed loop), its seed data, reset procedure and what must never break. Use when building or changing anything visible in the demo, writing the E2E test, preparing the pitch, or before a code freeze.
---
# Demo flow (5 minutes, matches VZP slide 12)

Roles are switched with the role switcher in the header (mock login). Demo date is simulated with
`STAFETA_DEMO_NOW` so the clock shows the right day in each step.

| # | Demo date | Role | Action | Must be visible |
| --- | --- | --- | --- | --- |
| 1 | 2. 10. 2026 | Praktický lékař (MUDr. Řezníček) | Drag & drop `07_PL_zadost_KOC2` → pick KOC 2 → confirm consent → Odeslat | Pre-filled patient and suspected diagnosis C25.0, no long form, state **Odesláno** |
| 2 | 2. 10. 2026 | Koordinátorka KOC 2 (Bc. Dvořáková) | Open new case in queue → Převzít | AI notice "výsledky 01–06 nejsou přiloženy" with one-click request tasks; state **V triage → Čeká na podklady** |
| 3 | 8.–19. 10. | Koordinátorka / lékař KOC | Upload 01–06 and 08–11 (or receive lab via HL7 v2) → Handover | 15 fields with source chips; **Chybí** ECOG, TNM, e-mail; **Nesouhlasí** apixaban dates and histology sample date; **Zastaralé** weight; doctor confirms sections |
| 4 | 2.–19. 10. | Koordinátorka | Start set "Karcinom pankreatu – diagnostika" | Tasks CT (KOC 1), EUS-FNB, odběry + TM, histologie, algeziolog, psycholog with owner, place, due date, dependencies; "kdo je na tahu" board; histology SLA escalation |
| 5 | 21. 10. 2026 | Lékař KOC / MDT | As-of 21. 10. → readiness gate → Generate MDT zápis | Reports 12–13 shown as "po MDT" and excluded; DOCX/PDF in MDT_zapis layout |
| 6 | 21. 10. 2026 | Koordinátorka → PL → revizní lékař ZP 211 | Send MDT conclusion → GP opens it → reviewer summary | Mailpit shows the e-mail; delivery + read receipt in audit trail; state **Uzavřeno**; T1/T2/T3 clock |

## Commands
```bash
make demo-reset      # wipes case data in IRIS, re-seeds directory (KOC 1, KOC 2, practices) and users
make seed            # loads documents in "received" order with the demo timestamps
make e2e             # Playwright runs all 6 steps, records video to frontend/e2e/artifacts/
```

## Never break
- Steps 1–6 must run end-to-end with `STAFETA_LLM_CACHE=1` (no network to APIM needed).
- No English strings, no stack traces, no empty states without guidance on screen.
- The as-of exclusion of reports 12–13 and the 2 date conflicts must always be visible.

## Fallbacks for the live demo
1. Cached LLM responses (default in demo mode). 2. Local docker stack if Azure is down.
3. The Playwright video from the last green `make e2e`.
