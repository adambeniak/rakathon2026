<!-- WHO: P4 · TOOL: Claude Code Sonnet 5.5 (or Copilot GPT-6.1 Sol) · MODE: normal · WHEN: F3 (04:00–08:00, "skřivan" shift) -->

ROLE: Backend engineer producing clinical documents that look exactly like what the KOC uses today.

CONTEXT: Handover (F2-2), findings (F3-1), readiness gate (F1-4) exist. Templates: `data/raw/MDT_zapis.docx`
(meeting record template) and `data/raw/MDT_zaver.docx` (example conclusion). Read the demo-flow skill (step 5).

GOAL: For MDT on 21. 10. 2026 the app produces the record "Zápis k jednání MDT" in the MDT_zapis structure, filled only
with data known by that date, and supports entering the MDT conclusion.

BUILD
1. `GET /api/cases/{id}/mdt/readiness?as_of=` → gate result (ready / missing / waived) using pathway requirements and
   open findings with severity high. Physician can waive an item with a reason (`POST .../mdt/waivers`).
2. `POST /api/cases/{id}/mdt/record` {mdt_date, members[]} → builds the record: basic data (patient, insurer name from
   code, phone + e-mail — e-mail shown as "neuvedeno" with a finding link, address, weight + height with dates),
   referring GP, MDT members, diagnosis (name + MKN-10), comorbidities, examinations table (date · exam · result —
   short result text with evidence link), empty Závěr/Doporučení. Persist as Composition (type MDT record).
3. Rendering: DOCX via `docxtpl` from a Jinja-tagged copy of MDT_zapis.docx (keep layout) and PDF from an HTML print
   template (WeasyPrint). `GET .../mdt/record.docx|pdf`. Add a footer "Vygenerováno aplikací Štafeta, údaje k <as_of>,
   zdroje v příloze" and an appendix listing source documents.
4. MDT conclusion entry: `PUT /api/cases/{id}/mdt/conclusion` {zaver, doporuceni[], presenting_physician, chair}
   — free text written by humans (for the demo, paste the text from MDT_zaver.docx); transition case to `zaver_mdt`.
   Optional: AI structures the pasted conclusion into recommendation items → Tasks (owner, due) as a DRAFT the
   coordinator confirms.
5. MDT mode UI contract for P3: agenda of cases for a given MDT date with readiness, one-click open of the record.

ACCEPTANCE
- [ ] Record for 21. 10. contains no data from reports 12–13 and shows all 9 examinations up to 19. 10.
- [ ] DOCX opens in Word/LibreOffice with the original layout; PDF renders Czech diacritics correctly
- [ ] `clinical-safety-reviewer` PASS; PR `wf/mdt-outputs`
