# Challenge brief (condensed for agents)

Source: VZP deck "Cesta pacienta bez ztráty informací" (16. 10. 2026), `data/raw/Zadani_ulohy.docx`,
`Handover_obsah.docx`, `MDT_zapis.docx`, `MDT_zaver.docx`. All patient data is fictitious.

## The problem (VZP slide 5)
Information is lost in three places: **at the entry** (documentation arrives fragmented, doctors retype data),
**inside the KOC** (coordinator spends time hunting documents; no shared view of state, deadlines and responsibility;
MDT gets late or incomplete input), **at the exit** (referring doctor cannot see whether the patient was accepted,
what is missing, what the MDT decided; delays are hard to track).
Context: MZ ČR created the coordinator role, VZP pays for it; KOCs treat ~65 % of patients and are overloaded.
Time to treatment = T1 (symptom → diagnostics) + T2 (diagnostics → MDT) + T3 (MDT → treatment).
In the demo we measure proxies (label them so in UI and pitch): T1 = first GP visit → KOC referral (symptom date is
only approximate), T2 = referral → MDT, T3 = MDT → oncology consult (treatment start not yet known). Coordinator types:
K1 before treatment, K2 during, K3 after.

## What the app must do (Zadani_ulohy)
1. **Převzít** — accept the GP's request for KOC 2 and the documents the GP hands over (no extra long form).
2. **Vyžádat a shromáždit** — coordinator requests missing reports from other workplaces; all documents in one place.
3. **Vytěžit** — AI extracts the Handover_obsah fields; flags missing or **inconsistent** data.
4. **Koordinovat** — plan and track steps (CT in KOC 1, biopsy, labs, algeziolog, psycholog) with date, place, state.
5. **Připravit podklad pro MDT** on 21. 10. 2026 using only data known by that date.
6. **Uzavřít smyčku** — send the MDT report to the GP and **prove delivery**; reviewer (revizní lékař) is informed automatically.
Rules: take data as written, do not infer; mark what is missing. Reports 12 and 13 were created after the MDT.

## Demo must show (slide 12)
Referral without a form · AI extraction with completeness check · case overview with state and deadline ·
owner of every next step · structured KOC/MDT conclusion · feedback with confirmed handover.
"AI only prepares a draft → a human decides and confirms." "Rakathon validates the principle; production integration is next."

## Case states (slide 10)
1 Odesláno · 2 V triage · 3 Čeká na podklady · 4 Kompletní · 5 Připraveno k rozhodnutí/MDT · 6 Závěr KOC/MDT ·
7 Zpětná vazba odeslána · 8 Uzavřeno (archived with audit trail). "At every moment it must be clear where the case is,
who holds the baton and by when the next step is due."
Coordinator queue (slide 9): Nový (čeká na převzetí) · Aktivní (probíhá diagnostika) · Odložený (čeká na externí krok).
Task sets per diagnosis (e.g. pancreatic cancer), sequencing (what must precede what), communication (e-mail/SMS/chat),
notifications for deadlines.

## Handover_obsah (15 groups)
1 Nacionále (jméno, příjmení, věk, pohlaví, číslo ZP) · 2 Kontakty (pacient, kontaktní osoba + tel.) · 3 Diagnóza ·
4 Epikríza · 5 Požadavek/otázka na MDT · 6 Komorbidity (OA) · 7 Léková anamnéza (FA) · 8 Alergie (AA) ·
9 PS / Karnofsky · 10 Váha a výška · 11 Symptomy a jejich počátek · 12 Provedená vyšetření (datum, místo, typ, plné znění) ·
13 Laboratoř vč. onkomarkerů · 14 Histologie · 15 Jiná důležitá sdělení vč. přání pacienta.

## MDT_zapis (output template)
Datum MDT; Pacient (jméno, pojišťovna, telefon + e-mail, adresa, váha + výška); Referující lékař (jméno, telefon + e-mail);
Členové MDT; Diagnóza (název + MKN-10); Komorbidity; Výsledky vyšetření (datum · vyšetření · výsledek); Závěr MDT; Doporučení MDT.

## Known traps in the data (must be detected — see data/golden)
Apixaban pause/resume dates after the biopsy date (report 09); histology sample date 20. 10. after issue date 19. 10.;
histology promised within 3 working days, delivered after 5; ECOG/Karnofsky missing; TNM missing; e-mails missing;
weight/height stale; GP control lab on 9. 9. never delivered; GP attached no results; reports 12–13 after MDT;
consent to share with daughter documented on 2. 10. but MDT text says "after her consent"; insurer 211 (ZP MV ČR), not VZP.
