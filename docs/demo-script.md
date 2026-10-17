# Demo script: click-by-click runbook, 6 steps

Status: **not yet dry-run on a live stack.** Everything below is derived from the code on `main` (UI strings in
`frontend/src/i18n/cs/`, routes, backend guards), not from a recorded run. The first full rehearsal on a fresh
`demo-start` is open (board #24, "Needs a human"). Where the code and the story disagree, the runbook says so and gives
the workaround. Labels in **bold** are the exact on-screen texts.

Presenter lines are Czech (spoken); everything else is English. All data is fictitious (Alena Procházková, MDT
21. 10. 2026 08:00). Due dates in the app are demo assumptions, not clinical guidance.

## Approved wording (say and show only this)

| Text on screen / in speech | Where it appears |
| --- | --- |
| **Návrh AI – čeká na potvrzení** | every handover section until a physician acts |
| **Potvrzeno lékařem** | section confirmed unchanged; summary line **Potvrzeno lékařem: n z 15** |
| **Upraveno lékařem** | section saved with the physician's own value (no source quote) |
| **Ponecháno jako chybějící** | physician accepted a missing value as missing (button **Ponechat jako chybějící**) |
| **Doplněno lékařem** | a missing value filled in by the physician (button **Upravit**) |
| **Chybí**, **Nesouhlasí**, **Zastaralé**, **Po MDT** | data-quality chips |

Never say or show **"Ověřeno"** or "Ověřeno lékařem". The string still exists in `frontend/src/i18n/cs/common.ts`
(`status.verified`); the handover overrides it with **Potvrzeno lékařem**, so it should not appear (check once in the
rehearsal; #123). Presenter wording stays neutral: "v dokumentaci uvedeno…", "nesoulad mezi…", "chybí…". The AI never
recommends treatment, doses or a diagnosis; never improvise clinical statements.

## Setup (once, before going on stage)

Local stack (the demo fallback and the only path rehearsed in the repo; `.iris/password.txt` holds any password):

```bash
make up-local                      # SCENARIO=demo-start (default): directory, users, patient. NO case, NO documents.
cd frontend && pnpm install && pnpm dev      # http://localhost:5173 (proxies /api to :8000; do NOT set VITE_MOCKS)
# mailpit inbox: http://localhost:8025
```

`make up-local` rebuilds and starts IRIS, backend and mailpit, seeds `demo-start`, and ends with `OK: …` or `FAIL: …`.
It runs with `STAFETA_DEMO_MODE=1` and `STAFETA_LLM_CACHE=1`. A backend restart also clears the demo clock override.
Do **not** run `make seed` (that is the `story` scenario: the finished case, which breaks step 1). On the shared team
ACI only the merge captain runs `make demo-reset`; agents never do.

Before step 1:

1. Open http://localhost:5173, role **Praktický lékař**, simulated date **2. 10. 2026** (the header switcher also
   moves the server clock; it pins it to 09:00).
2. Have the 13 reports ready in `data/raw/Pacient/`. **Upload every file under its original name**: the file name is
   the LLM cache key; a renamed file is a cache miss and the demo then needs APIM.
3. Open Mailpit and clear it.
4. Keep a **bash** terminal open in the repo root (the snippets use relative paths such as `data/raw/Pacient/…`; the
   machine's default shell may be fish, where `VAR=value` assignments do not work). Run once:
   `export BACKEND=http://localhost:8000` (and, after step 2, `export CASE=<case id>`).

### Clock cheat sheet

The header switcher offers 2. 10., 12. 10., 16. 10., 19. 10. and 21. 10. and sets the server clock to **09:00** of that
day. Any other moment needs `PUT /api/demo/clock`; **reload the page afterwards** (the UI reads the clock only on load).

| Step | Clock | How |
| --- | --- | --- |
| 1, 2 | 2. 10. 2026 | switcher |
| 3 | 20. 10. 2026 14:00 | curl (not a preset), see step 3 |
| 3b (upload 12, 13) | 28. 10. 2026 09:00 | curl, see step 3 |
| 4 | 2. 10. 2026, then 16. 10. 2026 | switcher, then `POST /api/demo/advance` |
| 5, 6 | 21. 10. 2026 09:00 (≥ 08:00, MDT start) | switcher |

Why 20. 10. for step 3 (#121): the as-of rule excludes a document authored **on or after** the as-of day. Report 11 is
authored 19. 10., so at 19. 10. it would be left out and the histology conflict would not show. Why uploads before step 4:
the handover for the MDT is cut at `mdt_start` (21. 10. 08:00, set at the launch in step 4); a document received after
that moment would be excluded.

```bash
# bash, repo root
curl -s -X PUT $BACKEND/api/demo/clock -H 'X-Demo-Role: coordinator' -H 'Content-Type: application/json' \
  -d '{"now": "2026-10-20T14:00:00+02:00"}'
```

`X-Demo-Role` values: `gp`, `coordinator`, `koc_physician`, `reviewer`. The case id appears in the browser URL
(`/cases/rakathon-2026-prochazkova-<6 hex>`); the commands below use `$CASE`.

## Known blockers and gaps of the UI (read before rehearsing)

| Gap | Effect | Workaround in this runbook |
| --- | --- | --- |
| The upload form never sends `request_id` (`frontend/src/features/documents/api.ts`); the backend closes a report request only with it (#120) | Uploading 01–06 in the UI leaves the 6 requests open, the case stays **Čeká na podklady** and never becomes **Kompletní**; the button **Označit jako připravený k MDT** only exists in **Kompletní** | Step 3: upload 01–06 with curl and `request_id` |
| `GET /handover` does not persist; only a section confirmation does; the readiness gate needs a handover persisted for `mdt_start` | **Označit jako připravený k MDT** is refused until a section has been confirmed after the launch | Step 5: confirm one section first |
| Confirmations are stored per (case, `as_of`); step 3 (`as_of` = 20. 10. 14:00) and step 5 (`as_of` = 21. 10. 08:00) are different snapshots (#122) | Step 3 confirmations do not appear in step 5 | Say so; confirm again in step 5 |
| Audit, Časová osa and Komunikace tabs use provisional endpoints that are not in the contract (#47) | They can fail against the real backend | Do not show them; use the proofs named in each step |
| Reviewer screen uses the provisional `/api/reviewer/cases` (#104, #105); the reviewer is not notified (#74) | **Přehled pro pojišťovnu** can fail; no automatic reviewer message exists | Skip the reviewer live; see step 6 |
| HL7 v2 ingestion is not implemented (no production under `iris/`, #126) | The older "or send the HL7 lab" option does not exist | Upload DOCX only |
| `make e2e` / `frontend/e2e` do not exist yet (#125) | No recorded run to fall back to | Fallbacks below |

## 1 · Referral without a form

- **Clock:** 2. 10. 2026 (switcher) · **Role:** Praktický lékař (MUDr. Tomáš Řezníček)
- **Click:**
  1. Header nav **Nová žádost** (route `/referral/new`).
  2. Drop `data/raw/Pacient/07_PL_zadost_KOC2_2026-10-02.docx` on **Přetáhněte sem žádost** (or **Vybrat soubor**).
  3. Wait for **Předvyplněný souhrn** (**Čtu dokument…**).
  4. **Cílové onkologické centrum** → KOC 2 (Nemocnice Lipová).
  5. Confirm **Naléhavost žádosti (potvrďte)** if the field is shown.
  6. Tick **Pacient/ka souhlasí se sdílením zdravotnické dokumentace s vybraným centrem.**
  7. **Odeslat do KOC**.
- **Must be visible:** pre-filled patient (**Pacientka**, **Datum narození**, **Rodné číslo**, **Pojišťovna**) and
  **Podezření / diagnóza** with C25.0; no long form; the sent screen **Odesláno**; **Přejít na moje pacienty** shows the
  case with state **Odesláno** and **Na tahu** = Koordinátor. If required data is missing in the letter, the screen
  blocks the send (**V žádosti nejsou uvedeny povinné údaje…**).
- **Say:** „Praktický lékař nevyplňuje žádný dlouhý formulář. Přetáhne žádost, Štafeta předvyplní údaje z dokumentu a
  lékař je před odesláním zkontroluje. Případ je Odesláno a na tahu je koordinátorka.“
- **Fallback:** the button **Použít ukázkovou žádost (07_PL_zadost_KOC2)** (not rehearsed against the real backend);
  otherwise restart with `make up-local SCENARIO=story`: that case is already in **Připraveno k rozhodnutí/MDT**, so
  only steps 5 and 6 can run on it.

## 2 · Triage and missing documents

- **Clock:** 2. 10. 2026 · **Role:** Koordinátorka KOC 2 (Bc. Lucie Dvořáková)
- **Click:**
  1. Nav **Fronta případů**, column **Nový**; on the card **Převzít** (or open the case, **Převzít**).
  2. The state becomes **V triage**. Open the case (**Otevřít případ**) and press **Vyžádat podklady**, which scrolls
     to **Chybějící podklady k vyžádání**.
  3. The panel marks the proposals **Návrh k vyžádání – zkontrolujte a odešlete.** and quotes the letter (hint chip
     from document 07). **Vybrat vše**, then **Vyžádat vybrané**.
- **Must be visible:** reports 01–06 as proposals with **Adresát** and the quote; after sending **Vyžádáno: 6.**; state
  **Čeká na podklady** (shown in the header badge).
- **Say:** „Koordinátorka případ převezme. Aplikace v žádosti najde odkazy na výsledky 01 až 06, které nejsou přiložené,
  a nabídne je k vyžádání. Nic se nepošle bez jejího potvrzení.“
- **Fallback:** the proposals come from the LLM cache; if the panel is empty or errors, say „tuto část ukážu ze
  záznamu“ and use the global fallbacks below.
- Copy the case id from the URL now: `export CASE=rakathon-2026-prochazkova-xxxxxx` (bash).

## 3 · Handover extraction

- **Clock:** set 20. 10. 2026 14:00 (curl above) and reload.
- **Role:** Koordinátorka (uploads) → Lékař KOC 2 (confirms). The physician is `doc. MUDr. Pavel Hrubý, Ph.D.`
- **Prepare (off stage, or quickly before the click part):**
  1. List the six requests and attach each report (the UI cannot, see the gap table):
     ```bash
     # bash, repo root
     curl -s $BACKEND/api/cases/$CASE/document-requests -H 'X-Demo-Role: coordinator'    # id + label of each request
     # for each report 01–06, pick the request whose label matches the report and send it with its id:
     curl -s -X POST $BACKEND/api/cases/$CASE/documents -H 'X-Demo-Role: coordinator' \
       -F file=@data/raw/Pacient/01_Kardiologie_2026-07-20.docx -F request_id=<id of the matching request>
     ```
     After the last one the case moves to **Kompletní** (response field `case_event`).
  2. Case tab **Dokumenty** → **Přidat zprávu k případu** → choose `08`, `09`, `10`, `11` →
     **Nahrát** (coordinator only). Each line shows **Nahráno: <file name>**.
  3. Clock 28. 10. 2026 09:00 (curl, reload); on **Dokumenty** upload `12_Algeziologie_2026-10-26.docx` and
     `13_Psychologie_KOC2_2026-10-27.docx`. Then continue at step 4. Doing this before the pathway launch keeps the
     watchdog from escalating anything at 28. 10.
  4. Clock 20. 10. 2026 14:00 again, reload, for the live part below.
- **Click (live):**
  1. Case tab **Handover**: **Stav k termínu** (20. 10. 2026 14:00) and **Souhrn handoveru**.
  2. Open the evidence of one value: **Zobrazit zdroj a citaci** shows document, **Vyhotoveno**, **Přijato** and the
     verbatim quote.
  3. Role **Lékař KOC 2**: on one section **Potvrdit sekci** (for example **Pacient**).
- **Must be visible:** 15 sections, each value with a source chip; **Chybí** (Stav výkonnosti, TNM in Diagnóza,
  e-mail in Kontakty) with **Může doplnit: …**; **Nesouhlasí** on Léková anamnéza (apixaban) and Histologie (date of
  sampling); **Zastaralé** on Výška a hmotnost; every unconfirmed section marked **Návrh AI – čeká na potvrzení**; the
  confirmed section **Potvrzeno lékařem** and **Potvrzeno lékařem: 1 z 15**; **Potvrdil(a) <name>** under it. Under
  the sections **Související zjištění** quotes the two date conflicts. The coordinator sees **Potvrdit sekci** disabled
  with **Potvrdit sekci může pouze lékař. Přepněte roli na „Lékař KOC 2“.**
- **Say:** „Z dokumentů vznikne handover o patnácti sekcích a u každé hodnoty je vidět zdroj a citace. Chybí stav
  výkonnosti, TNM a e-mail pacientky; datum posledního apixabanu a datum odběru histologie si v dokumentaci odporují;
  váha je zastaralá. Nic nedomýšlíme. Všechno je Návrh AI, dokud to lékař nepotvrdí.“
- **Proof of the audit trail:** the Audit tab is not reliable against the real backend (#47). If asked, say that every
  read and write is recorded in the audit trail (`AuditEvent`) and show the entry in Mailpit/step 6 instead.
- **Fallback:** pre-extracted answers come from the LLM cache (default); if the upload is slow, upload only `08` and
  `11` live and the rest beforehand.

## 4 · Coordination: who holds the baton

- **Clock:** 2. 10. 2026 (switcher; going back in time is intentional: say „vraťme se o pár dní zpět“) ·
  **Role:** Koordinátorka
- **Click:**
  1. Open the case, tab **Úkoly**, **Spustit sadu: Karcinom pankreatu – diagnostika**.
  2. Form: **Indikující lékař KOC** (default doc. MUDr. Pavel Hrubý, Ph.D.), **Začátek sady** 2. 10. 2026
     (defaults to the simulated date), **Plánovaný začátek MDT** 21. 10. 2026 08:00 (default) → **Spustit sadu**.
  3. The board **Kdo je na tahu** shows the lanes (PL, Koordinátor, Lékař KOC, Externí pracoviště, Pacient) with
     the tasks, each with **Místo**, **Termín** and **Čeká na: …**.
  4. Show a manual order confirmation on a step the replay does not touch: on **Algeziolog** press **Potvrdit
     objednání**, enter **Pracoviště** and **Datum vyšetření** → **Potvrdit** (a sent request is not an ordered
     examination). Do not do this on CT, EUS-FNB, odběry or histologie: the next substep replays them through the task
     machine and a hand-entered date could conflict with the story.
  5. Move the story to the escalation day. Reports 08, 09 and 10 must be uploaded already (step 3):
     ```bash
     # bash
     curl -s -X POST "$BACKEND/api/demo/advance?case_id=$CASE&to=2026-10-16" -H 'X-Demo-Role: coordinator'
     ```
     Reload the page (switcher now shows 16. 10. 2026).
- **Must be visible:** tasks CT (KOC 1), EUS-FNB, odběry + TM, histologie, algeziolog, psycholog, MDT with owner, place,
  due date and dependencies (demo assumptions, labelled as such); phases **K objednání → Objednáno → Provedeno →
  Výsledek doručen**; after the advance only the histology task is **Po termínu** (1 pracovní den) with **Slíbeno do**
  15. 10. and **Eskalováno 16. 10. 2026**.
- **Say:** „Sada vytvoří úkoly a každý má vlastníka, místo a termín. Termíny jsou demo předpoklad. Histologie byla
  slíbena do tří pracovních dnů od 12. 10., tedy do 15. 10. K 16. 10. je po termínu a koordinátorka dostane eskalaci.“
- **Fallback:** the board shows the same lanes from a freshly launched set; if `advance` answers 409 or 403, check
  that 08–10 are uploaded and that the header is `X-Demo-Role: coordinator`; otherwise skip the escalation and say it.

## 5 · MDT handover as of 21. 10. 08:00

- **Clock:** 21. 10. 2026 (switcher, 09:00) and reload · **Role:** Lékař KOC 2 (Koordinátorka for the download)
- **Click:**
  1. Nav **Fronta případů** → the case (state **Kompletní**, baton Lékař KOC).
  2. Tab **Handover**: **Stav k termínu** is now 21. 10. 2026 08:00. All sections are **Návrh AI – čeká na
     potvrzení** again (new snapshot). Confirm at least **one** section (**Potvrdit sekci**): this persists the
     handover the gate reads. On **Stav výkonnosti** press **Ponechat jako chybějící** (**Ponecháno jako chybějící –
     potvrdil(a) …**).
  3. **Připravit MDT** (page **Příprava MDT**, **Stav k začátku MDT: 21. 10. 2026 08:00**): **Souhrn handoveru k MDT**,
     **Nesoulady v dokumentaci**, and **Po MDT – nezahrnuto** with reports 12 and 13.
  4. **Označit jako připravený k MDT**. The server answers with the missing item **Stav výkonnosti (PS/ECOG)**; enter
     a **Důvod prominutí** and press **Prominout a označit jako připravený**. Result: **Případ je označen jako
     připravený k MDT.** and state **Připraveno k rozhodnutí/MDT**.
  5. **Stáhnout zápis (DOCX)** (file in the MDT_zapis layout; marked as a draft while not every section is confirmed).
- **Must be visible:** reports 12 and 13 only under **Po MDT – nezahrnuto** and as **Po MDT** in tab **Dokumenty**; the
  two date conflicts still listed; the waiver asks for a reason (recorded as who, when, why); the DOCX downloads under
  the app's own file name.
- **Say:** „K MDT použijeme jen to, co bylo známo k 21. 10. v 8:00. Zprávy 12 a 13 vznikly později, proto jsou označeny
  Po MDT a nejsou v podkladu. Server hlídá připravenost: stav výkonnosti v dokumentaci chybí. Lékař ho může vědomě
  prominout s odůvodněním, zaznamená se kdo a proč. Hodnotu nikdo nedomýšlí.“
- **Fallback:** `make up-local SCENARIO=story` seeds the case already in **Připraveno k rozhodnutí/MDT** with all 13
  documents and `mdt_start` 21. 10. 08:00; set the switcher to 21. 10. 2026, show the DOCX from the MDT page and go on
  with step 6.
- Do not fill in the missing performance status with a value the documents do not state. **Doplněno lékařem** (button
  **Upravit** on a missing section) is only for a value the physician takes from the patient, not for a demo shortcut.

## 6 · Closing the loop

- **Clock:** 21. 10. 2026 09:00 (must be ≥ 08:00; the conclusion is refused earlier)
- **Click:**
  1. Role **Lékař KOC 2** → case → **Připravit MDT** → **Závěr MDT**: paste the text from the fictitious
     `data/raw/MDT_zaver.docx` into **Text závěru MDT** → **Zapsat závěr MDT**. The signed block shows
     **Podepsaný závěr MDT**, **Podepsal(a) <name> · <time>**; state **Závěr KOC/MDT**, baton Koordinátor.
  2. Role **Koordinátorka KOC 2** → case → **Odeslat závěr** → **Odeslat závěr PL**. Shows **Závěr je předán k
     doručení praktickému lékaři.** and state **Zpětná vazba odeslána**.
  3. Mailpit (http://localhost:8025): message **Štafeta: zpětná vazba z MDT je k dispozici**. The mail has no clinical
     text, only a link to the GP portal.
  4. Role **Praktický lékař** → **Moji pacienti** → **Otevřít závěr MDT**: signed text with signer and time, and
     **Otevření závěru bylo zaznamenáno do auditní stopy.**
  5. Role **Koordinátorka** → case → tab **Handover** → **Připravit MDT** (the only link to the MDT page once the case
     is in **Zpětná vazba odeslána**) → **Uzavřít případ** → warning **Zda praktický lékař závěr otevřel, tato obrazovka
     nezjišťuje…** → **Uzavřít přesto** → **Případ je uzavřen.** State **Uzavřeno**.
- **Must be visible:** the e-mail in Mailpit; the GP reading the conclusion signed by the physician (**Podepsal(a)
  <name> dne <date>**); state **Uzavřeno**; the case header **Časové intervaly** (T1, T2, T3) as returned by the API or
  **zatím neběží**; they are proxies (T1 = první návštěva PL → žádost do KOC, T2 = žádost do KOC → MDT, T3 = MDT →
  onkologické konzilium) and must be called so.
- **Say:** „Závěr MDT podepíše lékař, koordinátorka ho odešle a praktickému lékaři přijde e-mail bez klinického
  textu. Otevření závěru se zapíše do auditní stopy. Případ je uzavřen. Intervaly T1, T2, T3 jsou zástupné hodnoty.“
- **Do not claim:** that the e-mail was *read* (the screen says „předáno k doručení“, the relay accepted it); that the
  insurer's reviewer is informed automatically (#74) or sees a scoped summary (#104, #105); that the app knows whether
  the GP opened the conclusion on the coordinator screen (#113).
- **Fallback:** a screenshot of the Mailpit message; if the send answers 503 (**E-mail se teď nepodařilo odeslat…**),
  the state did not change, so press **Odeslat závěr PL** again.

## Global fallbacks and reset

1. Cached LLM responses (default; original file names). 2. The local stack (`make up-local`) if Azure is down.
3. `make up-local SCENARIO=story` for a finished case (steps 5 and 6 only).
Reset between rehearsals: restart the backend (clears the clock) and re-seed with `make up-local` (it recreates the
local IRIS); on the shared ACI ask the merge captain. If a step stalls for more than 20 s say „tuto část ukážu ze
záznamu“ and go on; never improvise clinical statements.
