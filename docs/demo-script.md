# Demo script — 5 minutes, 6 steps

Presenter lines are in Czech (spoken); everything else in English. Roles are switched with the header
role switcher. Demo clock: `STAFETA_DEMO_NOW` (set per step). All data is fictitious (Alena Procházková,
MDT 21. 10. 2026 08:00). Due dates shown in the app are labelled **demo předpoklad**, not clinical guidance.
Run with `STAFETA_LLM_CACHE=1`. Before going on stage: `make demo-reset && make seed`.

Timing budget: 0:00 intro · 0:20–4:40 six steps · 4:40–5:00 closing. Two people: **A** speaks, **B** clicks
(or one person doing both — then keep the "say" lines to one sentence).

| # | Time | Clock (`STAFETA_DEMO_NOW`) | Role (switcher) |
| --- | --- | --- | --- |
| 1 | 0:20–1:00 | 2026-10-02T09:00 | Praktický lékař (MUDr. Řezníček) |
| 2 | 1:00–1:45 | 2026-10-02T11:00 | Koordinátorka KOC 2 (Bc. Dvořáková) |
| 3 | 1:45–2:45 | 2026-10-19T14:00 | Koordinátorka → lékař KOC |
| 4 | 2:45–3:30 | 2026-10-16T09:00 | Koordinátorka |
| 5 | 3:30–4:15 | 2026-10-21T08:00 | Lékař KOC / MDT |
| 6 | 4:15–4:55 | 2026-10-21T12:00 | Koordinátorka → PL → revizní lékař ZP 211 |

Step 4 is deliberately shown at 16. 10. (the escalation day) after step 3, then step 5 jumps forward; say
"vraťme se o pár dní zpět" when switching the clock.

## 1 · Referral without a form (0:20–1:00)
- **B clicks:** drag & drop `07_PL_zadost_KOC2` → select KOC 2 → tick consent → **Odeslat**.
- **A says:** „Praktický lékař nevyplňuje žádný dlouhý formulář. Přetáhne epikrízu, Štafeta předvyplní pacientku
  a podezření na diagnózu C25.0. Případ je ve stavu Odesláno a na tahu je koordinátorka.“
- **Proof on screen:** pre-filled patient, state **Odesláno**, baton = Koordinátor.
- **Fallback:** pre-seeded case in "Nový" via `make seed`; skip straight to step 2.

## 2 · Triage and missing documents (1:00–1:45)
- **B clicks:** queue **Nový** → open case → **Převzít** → AI notice → one-click **Vyžádat** for reports 01–06.
- **A says:** „Koordinátorka případ převezme. Aplikace upozorní: ‚výsledky 01–06 nejsou přiloženy‘ a jedním
  klikem založí úkoly na vyžádání. Případ čeká na podklady.“
- **Proof:** state **V triage → Čeká na podklady**, 6 request tasks with owner and due date.
- **Fallback:** cached notice (LLM cache); if the click fails, use the task list "Vyžádat vše".

## 3 · Handover extraction (1:45–2:45)
- **B clicks:** upload 01–06 and 08–11 (or send the HL7 v2 lab) → **Handover** → expand evidence chips → confirm one section.
- **A says:** „Z dokumentů vznikne handover o 15 skupinách, u každé hodnoty je zdroj. Chybí ECOG, TNM a e-mail.
  Nesouhlasí data u apixabanu a datum odběru histologie. Váha je zastaralá. Nic nedomýšlíme — údaje jsou
  návrh AI, dokud je lékař nepotvrdí.“
- **Proof:** chips **Chybí** (ECOG, TNM, e-mail), **Nesouhlasí** (apixaban, histologie), **Zastaralé** (váha),
  **Ověřeno lékařem** on the confirmed section; audit entries for each read/write.
- **Fallback:** pre-extracted handover from the LLM cache; if upload is slow, upload only 08 and 11 live.

## 4 · Coordination and "kdo je na tahu" (2:45–3:30)
- **B clicks:** **Spustit sadu** "Karcinom pankreatu – diagnostika" (start 2. 10.) → board "Kdo je na tahu" → histology task.
- **A says:** „Sada vytvoří úkoly: CT v KOC 1 do 8. 10., EUS-FNB 12. 10., odběry 15. 10., histologie 19. 10., MDT
  21. 10. — termíny jsou demo předpoklad. Každý krok má vlastníka, místo a závislosti. Histologie byla slíbena do
  tří pracovních dnů od 12. 10., tedy do čtvrtka 15. 10. — v pátek 16. 10. přijde koordinátorce eskalace.“
- **Proof:** task list with owner/place/due/dependencies; escalation banner on histology (basis: SLA, 1 pracovní den po termínu);
  order status shows **objednáno → potvrzeno → provedeno → výsledek doručen**.
- **Fallback:** seeded tasks via `make seed`; set `STAFETA_DEMO_NOW=2026-10-16T09:00:00+02:00` and reload.

## 5 · MDT handover as-of 21. 10. (3:30–4:15)
- **B clicks:** set as-of 21. 10. 08:00 → readiness gate → (ECOG missing → physician **Prominout** with a reason) → **Generovat MDT zápis** → open DOCX/PDF.
- **A says:** „K jednání MDT použijeme jen to, co bylo známo k 21. 10. v 8:00. Zprávy 12 a 13 vznikly po MDT, proto jsou
  označeny ‚po MDT‘ a nejsou v podkladu. Brána připravenosti ukazuje, že chybí stav výkonnosti; lékař ji může
  s odůvodněním prominout — zaznamená se kdo a proč.“
- **Proof:** reports 12–13 greyed "po MDT" and excluded; the two date conflicts still visible; gate result
  `{ready, missing, waived}`; document in MDT_zapis layout; state **Připraveno k MDT**, baton = MDT.
- **Fallback:** pre-generated MDT_zapis file from the last green `make e2e` artifacts.

## 6 · Closing the loop (4:15–4:55)
- **B clicks:** record conclusion (confirm) → **Odeslat praktickému lékaři** → open Mailpit → switch to PL, open the message → switch to revizní lékař ZP 211 → summary → **Uzavřít**.
- **A says:** „Závěr MDT odejde praktickému lékaři. Doručení a přečtení jsou doložené v audit stopě a revizní lékař
  pojišťovny 211 je informován automaticky. Případ je Uzavřen a máme měření T1, T2, T3 — jako zástupné hodnoty.“
- **Proof:** Mailpit message; audit entries `delivery_confirmed` and `gp_opened`; state **Uzavřeno**; T1/T2/T3 clock.
- **Fallback:** Mailpit screenshot / the Playwright video of the last green `make e2e`.

## Global fallbacks
1. Cached LLM responses (default). 2. Local docker stack if Azure is down. 3. Video from the last green `make e2e`.
If a step stalls for > 20 s, say „tuto část ukážu ze záznamu“ and jump to the next step; never improvise clinical statements.
