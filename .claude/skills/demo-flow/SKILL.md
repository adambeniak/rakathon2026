---
name: demo-flow
description: The canonical 6-step Štafeta demo (referral → triage → extraction → coordination → MDT handover → closed loop), its seed data, reset procedure and what must never break. Use when building or changing anything visible in the demo, writing the E2E test, preparing the pitch, or before a code freeze.
---
# Demo flow (6 steps, matches VZP slide 12)

**Source of truth: `docs/demo-script.md`.** It holds the click path, roles, clocks, exact on-screen labels, presenter
lines, known UI gaps and per-step fallbacks, derived from the code on `main`. Do not copy its step table here; read it
and keep it current when you change anything visible in the demo.

Steps: 1 referral without a form (PL) · 2 triage and missing documents (Koordinátorka) · 3 handover extraction
(Koordinátorka uploads, Lékař KOC confirms) · 4 coordination, "Kdo je na tahu" (Koordinátorka) · 5 MDT handover as of
21. 10. 2026 08:00 (Lékař KOC) · 6 closing the loop (Lékař KOC → Koordinátorka → PL). Fictitious patient Alena
Procházková.

## Facts that are easy to get wrong
- Clock: the header switcher (presets 2., 12., 16., 19., 20., 21. 10.) also moves the server clock to 09:00 of that
  day; other moments need `PUT /api/demo/clock`. `STAFETA_DEMO_NOW` pins the clock at startup.
- Step 3 runs at **20. 10.**, not 19. 10.: report 11 is authored 19. 10. and the as-of rule excludes a document
  authored on or after the as-of day, so at 19. 10. the histology conflict would not show (#121).
- As-of is decided by the backend and only displayed (**Stav k termínu**); there is no as-of picker in the UI.
- Documents arrive by upload only (tab **Dokumenty**, original file names = LLM cache keys). HL7 v2 ingestion is not
  implemented (#126).
- The MDT record is a **Stáhnout zápis (DOCX)** download on the **Příprava MDT** page; there is no "Generate" button
  and no PDF (#89).
- `make e2e` / `frontend/e2e` do not exist yet (#125): there is no Playwright run or video to fall back to.

## Commands
```bash
make up-local                  # demo fallback in ONE command: local IRIS + bootstrap + seed (SCENARIO=demo-start:
                               #   directory, users, patient, NO case) + backend + mailpit + health check OK/FAIL.
                               #   Also the reset between rehearsals (recreates the local IRIS).
make up-local SCENARIO=story   # finished case in "Připraveno k rozhodnutí/MDT" with all 13 documents: steps 5-6 only
make demo-reset                # = python -m app.seed --reset --scenario demo-start: deletes resources tagged
                               #   stafeta-demo, then seeds directory, users, patient. Shared ACI: merge captain only.
make seed                      # = scenario "story" (idempotent). Development only; it pre-creates the case and breaks
                               #   step 1. Never run it after demo-reset to prepare the demo.
```

## Never break
- Steps 1–6 run end-to-end with `STAFETA_LLM_CACHE=1` (no network to APIM needed), uploads under original file names.
- The as-of exclusion of reports 12–13 (**Po MDT**) and the 2 date conflicts (apixaban, histology sampling date) are
  always visible; missing values stay **Chybí** (never inferred, e.g. no ECOG from "soběstačná").
- Approved wording only: **Návrh AI – čeká na potvrzení**, **Potvrzeno lékařem**, **Upraveno lékařem**, **Ponecháno
  jako chybějící**, **Doplněno lékařem**. "Ověřeno" and "Zkontrolováno" are banned (`frontend/src/i18n/wording.test.ts`).
- No English strings, no stack traces, no empty states without guidance on screen.

## Fallbacks for the live demo
1. Cached LLM responses (default in demo mode). 2. Local stack (`make up-local`) if Azure is down.
3. `make up-local SCENARIO=story` for a finished case (steps 5 and 6 only). Per-step fallbacks: `docs/demo-script.md`.
