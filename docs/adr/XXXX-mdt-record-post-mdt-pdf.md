# ADR-XXXX: MDT record after the meeting (signed conclusion) and as PDF

- Date: 2026-10-17 · Status: proposed (additive contract change and a new dependency, approved by the repo owner) ·
  Owner: P4 · Issues: #92, #89
- The number is assigned by the merge captain; until then the file is named `XXXX-<slug>.md`.

## Context
- `GET /cases/{id}/mdt-record` (#73) renders the MDT_zapis form as DOCX, always as of `mdt_start`. Sections 6
  (Závěr MDT) and 7 (Doporučení MDT) said "Vyplní lékař na jednání MDT", section 2 (Členové MDT) "Chybí – prezence
  není zaznamenána". After the meeting the signed conclusion (`Composition` type `mdt-conclusion`, written by
  `record_mdt_conclusion`, #85) existed but the record never showed it (#92).
- PDF was not offered: the image has no DOCX→PDF converter (#89).

## Decision
- **One endpoint, no stage parameter.** Once a KOC physician has signed the MDT conclusion, the same export prints it.
  Before the sign-off the export is what it was. We rejected `?stage=po_mdt`: it adds a control to the demo and lets
  someone download a record without the conclusion after the meeting. A re-export of the pre-meeting basis after the
  sign-off is not offered on purpose (the handover snapshot as of `mdt_start` stays stored and readable via
  `/handover`).
- **As-of.** Sections 1–5 and the appendices stay strictly as of `mdt_start`; reports 12 and 13 stay "po MDT". The
  conclusion is the meeting's output, not an input document, so the as-of rule for the handover does not cover it.
  Only a conclusion signed **at or after** `mdt_start` is printed (the state machine already refuses an earlier one;
  a conclusion of an earlier, moved meeting is never printed under a later date). The meta line says
  "Závěr MDT podepsán lékařem <kdo>, <kdy> (oddíl 6)", so "Stav podkladů k 08:00" next to a 09:30 signature does not
  read as a contradiction.
- **Section 6** = label "Potvrzeno lékařem (<jméno>, <datum> <čas>)" (the shape of every confirmed section), a grey
  note "Text závěru MDT tak, jak jej lékař zapsal a podepsal; systém jej nemění ani nedoplňuje (rodná čísla
  vynechána)" and the signed text in the form's box. The text goes through the same sanitiser as every other value:
  line breaks kept, XML-illegal and layout control characters dropped, **birth numbers replaced by
  "[RČ vynecháno]"** (minimisation; the marker is visible). Otherwise the text is not touched.
- **Section 7** has no data source of its own. It is never filled by splitting the signed text at a "DOPORUČENÍ"
  heading, because that would mean the system interprets clinical text. After the sign-off it says "Samostatně zapsáno
  není. Doporučení MDT, pokud je lékař uvedl, je součástí podepsaného závěru v oddílu 6. Systém doporučení
  nevytváří."; before, "Vyplní lékař na jednání MDT…" as now.
- **Section 2 (members) unchanged: "Chybí – prezence členů MDT není v systému zaznamenána."** We preferred an optional
  `members` field on the `record_mdt_conclusion` payload, stored in the conclusion Composition. It has to go through
  `ClosedLoopWorkflow.record_conclusion` (`backend/app/api/services/closed_loop.py`), which another task (#149) is
  changing right now, so it is deferred to a follow-up issue (see PR "Not done").
- **Draft marking is unchanged**: banner, page header and the `NAVRH` file name depend on the handover sections only.
  A signed conclusion in a record with unconfirmed sections is still a draft record.
- **Reading the conclusion** goes through the existing `ClosedLoopWorkflow.get_conclusion` (audited read of the
  Composition, signer resolved from the directory); 404 = no conclusion. The export's derived-write `AuditEvent` also
  names `Composition/<id>` when the conclusion is printed.
- **PDF (`format=pdf`)**: rendered in-process by **reportlab 4.4.4** (pure Python wheel; its only dependencies,
  Pillow and charset-normalizer, were already in `uv.lock`). No LibreOffice, no system fonts: **DejaVu Sans** regular
  and bold (Bitstream Vera licence, redistribution allowed with the notice, `backend/app/outputs/fonts/LICENSE.txt`)
  are bundled (~1.4 MB) and embedded as subsets, so Czech diacritics render in every viewer. No oblique face is
  bundled; notes are grey, as in the DOCX.
- **One document model, two renderers.** `build_context` returns renderer-neutral values (`Rich` runs, strings,
  lists), all sanitised; the DOCX path maps `Rich` to docxtpl `RichText`, the PDF path to escaped reportlab paragraph
  markup. Same content, labels, waivers, banner and footer by construction; a test checks every model value appears in
  the PDF. Every text is XML-escaped before reportlab sees it. A zero-size marker flowable after the footer proves the
  layout reached the end; otherwise `MdtRecordError` (500), as the DOCX completeness check. Table rows split across
  pages, so a conclusion longer than a page cannot break the layout. PDF metadata: title "Zápis z jednání MDT",
  author "Štafeta", fixed timestamps (`invariant`), no patient data.
- **Contract (additive)**: `format` enum `docx | pdf` (default `docx`), 200 documents both media types. The frontend
  offers "Stáhnout zápis (PDF)" next to "Stáhnout zápis (DOCX)".

## Consequences
- Demo step 6: after **Zapsat závěr MDT** the same download buttons give the record with the signed conclusion.
- The pre-meeting record cannot be downloaded again once a conclusion is signed (by design, see above).
- reportlab is a new runtime dependency (~2 MB); `uv.lock` changed.
- Members and a separate physician-entered recommendation stay open (follow-up issues).
