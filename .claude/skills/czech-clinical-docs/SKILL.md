---
name: czech-clinical-docs
description: Czech clinical documentation glossary and parsing rules (abbreviations OA/FA/AA, PS/ECOG, MKN-10, MKN-O, rodné číslo, insurer codes, Czech dates, units, dosing notation 1-0-1, negation cues, working days). Use when parsing, extracting, validating or displaying Czech medical reports, or writing Czech clinical UI copy.
---
# Czech clinical documents — what an engineer must know

## Section abbreviations in reports
| Abbr. | Meaning | Handover field |
| --- | --- | --- |
| OA | osobní anamnéza (past history, comorbidities) | Komorbidity |
| FA | farmakologická anamnéza (current medication) | Léková anamnéza |
| AA | alergologická anamnéza; "neguje" = no known allergy | Alergie |
| RA / SA / PA | rodinná / sociální / pracovní anamnéza | Jiná sdělení (only if relevant) |
| Abusus | smoking, alcohol | Jiná sdělení |
| PS | performance status: ECOG 0–4 or Karnofsky 0–100 % | Stav výkonnosti — never infer from "soběstačná" |
| TM | tumour markers (CA 19-9, CEA, CA 125) | Laboratoř |
| PL | praktický lékař (GP) | — |
| KOC / ROC | komplexní / regionální onkologické centrum | — |
| MDT | multidisciplinary tumour board | — |
| EUS-FNB | endoscopic ultrasound fine-needle biopsy | Vyšetření |
| VMS / AMS | v. / a. mesenterica superior | (CT text) |
| st. p. | status post | Komorbidity |
| p. p. | pro re nata (as needed) | Léky |
| TK / TF / TT | blood pressure / heart rate / temperature | — |
| LSPP | out-of-hours emergency service | — |
| IČP | provider workplace ID | Organization identifier |

## Identifiers
- **Rodné číslo (RČ)** `YYMMDD/XXXX`. Women: month + 50 (and +70 for rare overflow series). Ten-digit RČ
  must be divisible by 11 (legacy exception: remainder 10 → check digit 0). Year: if YY ≥ 54 → 19YY, else 20YY
  (for 10-digit numbers). Demo: `635722/1013` → female, born 22. 7. 1963, checksum valid.
- **Insurer codes (kód ZP):** 111 VZP ČR · 201 VoZP · 205 ČPZP · 207 OZP · 209 ZPŠ · 211 ZP MV ČR · 213 RBP.
  The demo patient is insured by **211**, not VZP.
- Diagnosis codes: **MKN-10** = Czech ICD-10 (e.g. C25.0 head of pancreas). Histology morphology:
  **MKN-O** = ICD-O-3 (e.g. 8500/3 ductal adenocarcinoma).

## Dates and numbers
- Formats: `21. 10. 2026`, `4.11.2026 10:30`, `20. 7.` (year from context), relative ("od poloviny srpna",
  "3 měsíce před diagnózou"). Store ISO; keep the original string in evidence.
- Distinguish clinical date (examination/collection) from issue date ("Vydáno") and print/sign date.
- Decimal comma (`1,62`), units: µkat/l (enzymes), µmol/l, mmol/l, g/l, mg/l, kU/l, µg/l, 10⁹/l, 10¹²/l.
  Flags `H`/`L` after the value. Ranges written `0,10–0,60`.
- Dosing `1-0-1` = morning–noon–evening; `0-0-1` = evening only; "max. 4× denně".
- Working days: Mon–Fri excluding Czech public holidays (28. 10. and 17. 11. fall in the demo period).
  Example: "výsledek do 3 pracovních dnů" from Mon 12. 10. 2026 → due Thu 15. 10. 2026.

## Negation and uncertainty cues (respect them in extraction)
Negation: `neguje`, `bez`, `není`, `nebyl(a)`, `negativní`, `nezvětšen(y)`, `neprokázán`.
Uncertainty: `suspektní`, `susp.`, `vs.`, `diferenciálně diagnosticky`, `nelze spolehlivě posoudit`,
`k potvrzení`, `pravděpodobně`. A suspected diagnosis is not a confirmed one — keep `verificationStatus`.

## Report types → LOINC document codes (suggested)
GP referral/epicrisis 57133-1 (Referral note) · outpatient specialist report 11488-4 (Consult note) ·
lab report 11502-2 · imaging (X-ray, US, CT) 18748-4 · procedure protocol 28570-0 · pathology 11526-1 ·
MDT record / tumour board 85208-7 (verify in LOINC before use; otherwise use a local code and list it).

## UI copy rules
Use Czech clinical vocabulary the users already use (epikríza, nacionále, MDT, KOC, koordinátor,
revizní lékař). Statuses: **Chybí**, **Nesouhlasí**, **Zastaralé**, **Potvrzeno lékařem** (also **Upraveno lékařem**, **Ponecháno jako chybějící**), **Návrh AI**. Never "Ověřeno" or "Zkontrolováno".
Never write advice ("doporučujeme…") in AI-generated text; use "v dokumentaci uvedeno…".
