# FHIR R4 mapping

Domain ↔ FHIR lives only in `backend/app/fhir/mappers/`; URIs only in `backend/app/fhir/systems.py`.
Update this file in the same PR as any mapper change. Profiles to follow where practical: CZ Core (hl7.cz/fhir/core),
mCODE STU4 for cancer condition/staging. Decision record: [ADR-0001](adr/0001-iris-fhir-system-of-record.md).

## Domain → FHIR
| Domain concept | FHIR R4 | Key elements | Status |
| --- | --- | --- | --- |
| Patient (`domain.patient.Patient`) | `Patient` | identifier RČ (digits, no slash), name, gender, birthDate, telecom phone, address, generalPractitioner → GP `PractitionerRole` | F1 `mappers/patient.py` |
| Contact person | `RelatedPerson` | patient, relationship v3-RoleCode (`dcera` → `DAU`) + text, name, telecom | F1 |
| Insurance | `Coverage` | beneficiary, payor → insurer `Organization` + identifier `kp|211`, type `PUBLICPOL` | F1 |
| Workplace (`domain.directory.Organization`) | `Organization` | identifier slug (+ IČP, kód pojišťovny), type (`organization-type` prov/pay + our `organization-kind`), address, telecom | F1 `mappers/directory.py` |
| Person / role | `Practitioner` + `PractitionerRole` | name with prefix/suffix titles; role code = our `workflow-role`, specialty text as written | F1 |
| Case (`domain.case.Case`) | `EpisodeOfCare` + coordinating `Task` | EoC: identifier case id, status, type `oncology-diagnostics`, patient, managingOrganization (KOC), careManager (coordinator), period.start. Task: code `coordinate-case`, businessStatus `case-state`, focus → EoC, for → Patient, requester GP, owner = baton holder (reference + identifier + display), performerType = workflow role, restriction.period.end = next deadline, authoredOn = referral received | F1 `mappers/case.py` |
| Source document (`domain.document.SourceDocument`) | `DocumentReference` | identifier `source-document|<file stem>`, status current, docStatus final, type LOINC, subject, **date = received**, author → `PractitionerRole`, custodian → `Organization`, description = Czech title, context.encounter → case `EpisodeOfCare`, content.attachment: contentType, **base64 data**, size, hash (SHA-1), title = file name, **creation = authored** | F1 `mappers/document.py` |
| Audit | `AuditEvent` | type `rest`, subtype restful-interaction (create/read/search-type/update/delete/transaction), action C/R/U/D/E, recorded (UTC), agent (workflow role, who = identifier `user|<id>` + display, requestor), source.observer display "Štafeta backend", entity.what = references | F1 `audit.py` |
| Referral (žádost PL) | `ServiceRequest` | identifier `service-request|<case id>`, intent order, priority urgent, requester GP, performer KOC, reasonCode ICD-10 (code + text as written, suspected), supportingInfo → letter DocumentReference, note = GP's note; the case Task points to it with `basedOn` | F2-1 `mappers/referral.py` |
| Step / ad-hoc task (`domain.task.Task`) | `Task` partOf case Task | identifier `case-step|<task id>`, groupIdentifier = case id, status (`in_progress` → `in-progress`), intent order, code `task-code|<step code>` (`ad-hoc` for single tasks), description = Czech title, `location` = workplace (display only), `businessStatus` (`task-business-status`), performerType = effective owner role, owner = Reference with identifier + display only (no PractitionerRole lookup in the PoC; KOC-physician steps start with the indicating physician, a practitioner acting in the step's own role takes over, on-behalf recording never sets it — #137), `restriction.period.end` = due, `executionPeriod.start` = confirmed date/time (deviation, see notes), `output` = result document (identifier `source-document|<doc id>`; set by a transition or automatically when the matching report — step code → LOINC `DocumentReference.type` — is received, see `domain/task_results.py`, #132; for the `mdt` step the result is the signed MDT conclusion: valueReference type `Composition`, identifier `mdt-conclusion|<case>@<UTC instant>`, set when the conclusion is signed, #149), `statusReason` (reason of failed / cancelled), note (e.g. the source when the coordinator recorded progress for a workplace), extensions `depends-on` (repeats, business ids), `sla-due`, `escalated-at`, `ad-hoc`, `demo-assumption`, `recorded-on-behalf-by` | F2-4 `mappers/task.py` |
| Pathway template | `PlanDefinition` | url `…/PlanDefinition/pancreas-dx` (conditional create by `url`), actions with `relatedAction` `after-end`; extensions `due-rule`, `sla-rule`, `place`, `owner-role`, `mdt-required-items`; all offsets labelled DEMO ASSUMPTION | F1-4 `mappers/plan_definition.py`, seeded by `make seed` |
| Launched pathway | `CarePlan` + `ServiceRequest` per step + `Provenance` | CarePlan: identifier `careplan|<case id>.<plan key>`, instantiatesCanonical = PlanDefinition url, status active, intent plan, subject, **author = indicating KOC physician (PractitionerRole)**, created, period.start, activity.reference → step Tasks. ServiceRequest (one per step): identifier `case-step-order|<task id>`, status active, intent order, code `pathway-action|<step code>`, subject, authoredOn, **requester = indicating physician**, extension `demo-assumption`; the step Task points to it with `Task.focus`. Provenance: target = CarePlan + ServiceRequests, activity CREATE, agent = coordinator (`author`) with **`onBehalfOf` = indicating physician**. All written in **one transaction** (`If-None-Exist` on the CarePlan, ServiceRequests and Tasks). The launch requires `indicated_by` (422 without it) | F2-4 `mappers/care_plan.py`, `service_request.py`, `provenance.py` |
| Lab result | `Observation` (LOINC) in `DiagnosticReport` | effectiveDateTime = collection time | F2/F3-5 |
| Diagnosis | `Condition` (mCODE PrimaryCancerCondition idea) | category encounter-diagnosis, code ICD-10 + text, verificationStatus provisional → confirmed (histology), morphology ICD-O-3 in the mCODE `histology-morphology-behavior` extension | F2-2 `mappers/handover.py` |
| Comorbidity | `Condition` | category problem-list-item, code ICD-10 if stated + text, `note` = detail as written | F2-2 |
| Medication (handover field 7) | `MedicationStatement` | status active, medicationCodeableConcept.text = drug as written, dosage.text = dose + schedule, dateAsserted | F2-2 |
| Weight/height, lab, histology values | `Observation` | category vital-signs (LOINC 29463-7 / 8302-2, UCUM) or laboratory (code.text = test as written), valueQuantity/valueString, effectiveDateTime, interpretation H/L | F2-2 |
| Handover | `Composition` (preliminary → final) | identifier `sid/handover|<case>@<as_of UTC>`, type `composition-type|handover`, author = Device (logical), extensions episode + as_of; 15 sections: code `handover-section|<key>`, generated narrative, `handover-field-status` + `handover-review` extensions, `handover-edited-value` after an edit, `emptyReason` unavailable when missing, entries → derived resources / DocumentReferences (field 12) / Patient (field 1); `final` + `attester` (professional) when all 15 are confirmed or accepted as missing; a new snapshot (other as_of) carries over the latest physician decision per section whose value hash, field status and conflicts are unchanged (ADR handover-confirmation-carry-over) | F2-2 `mappers/handover.py`, `handover_store.py` |
| MDT record | `Composition` | sections = MDT_zapis | F3-3 |
| AI evidence | `Provenance` | target = derived resource (or the Composition, activity `assemble`), activity `extract`, agent assembler = Device (model + prompt versions), entity.role source, what = DocumentReference, `evidence-quote` extension (quote, charStart, charEnd) | F2-2 |
| Physician confirmation | `Provenance` | target = Composition, activity confirm / edit / accept-missing, agent verifier = PractitionerRole (business identifier + display, workflow role), extensions `handover-section` + `previous-value-sha256` | F2-2 |
| Carried-over decision | `Provenance` | target = the new handover Composition, activity `carry-over`, agent assembler = Device (the only agent: nobody confirms anything at copy time), entity source = the earlier Composition as a versioned reference with entity.agent verifier = the physician who decided (original time stays in `handover-review.at`), extension `handover-section`; same transaction as the Composition | #122 `mappers/handover.py` |
| MDT readiness waiver | `Provenance` | target = the coordinating `Task`, activity `provenance-activity|waive-readiness`, agent verifier = the acting KOC physician (PractitionerRole identifier + display, workflow role), `reason.text` = the physician's reason, extension `readiness-item`; written in the same transaction as the `mark_ready_mdt` Task update and its `AuditEvent` (detail `waived`) | #68 `mappers/readiness.py`, `readiness.py` |
| Consent / wishes | `Consent` | identifier `consent|<case id>`, scope patient-privacy, patient, organization KOC, sourceReference letter, provision permit/disclose to the KOC; statements of the letter verbatim in `consent-statement` extensions (not interpreted) | F2-1 |
| Messages | `CommunicationRequest` / `Communication` | request missing reports (fixed template + label as written in the letter; status `active` → `completed` when the report arrives); MDT result to GP; `received` = delivery proof | F2-1 / F3-4 |
| Report request step | `Task` code `request-report` | partOf case Task, basedOn CommunicationRequest, owner coordinator, `restriction.period.end` = due (+2 working days), `restriction.recipient` = workplace, businessStatus `objednano` → `vysledek_dorucen`, `output` = delivered DocumentReference, extension `request-exam-date` | F2-1 `mappers/document_request.py` |
| GP confirmation of the AI prefill | `Provenance` | target = resources created by the referral transaction, agent verifier = GP PractitionerRole, entity source = letter DocumentReference, extensions `prefill-comparison` (`compared`/`not-compared`), `prefill-edited-fields`, `prefill-added-fields` (field names only) | F2-1 |

## Identifier systems (`identifier.system`)
| System | Used for | Value |
| --- | --- | --- |
| `https://stafeta.example/fhir/sid/organization` | Organization | slug, e.g. `koc2-nemocnice-lipova` |
| `https://stafeta.example/fhir/sid/practitioner` | Practitioner | slug, e.g. `reznicek-tomas` |
| `https://stafeta.example/fhir/sid/practitioner-role` | PractitionerRole; also `Task.owner.identifier`, `EpisodeOfCare.careManager.identifier` | `<practitioner>@<organization>` |
| `https://ncez.mzcr.cz/fhir/sid/rcis` | Patient rodné číslo (CZ Core: `fixedUri` of `cz-rodcis-identifier`, hl7.cz/fhir/core 1.0.0), `use: official` | digits without slash, `6357221013` |
| `https://stafeta.example/fhir/sid/related-person` | RelatedPerson | `<rč>-<relation>` |
| `https://stafeta.example/fhir/sid/coverage` | Coverage | `<insurer code>-<rč>` |
| `https://stafeta.example/fhir/sid/case` | EpisodeOfCare | case id, e.g. `rakathon-2026-prochazkova` |
| `https://stafeta.example/fhir/sid/case-task` | coordinating Task | case id |
| `https://stafeta.example/fhir/sid/case-step` | step / ad-hoc Task | domain task id, e.g. `rakathon-2026-prochazkova.ct`, `…adhoc-1a2b3c4d` |
| `https://stafeta.example/fhir/sid/case-step-order` | ServiceRequest of a pathway step | domain task id |
| `https://stafeta.example/fhir/sid/careplan` | CarePlan | `<case id>.<plan key>` (plan key = last segment of the PlanDefinition url) |
| `https://stafeta.example/fhir/sid/source-document` | DocumentReference | file stem (= `doc_id` in evidence) |
| `https://stafeta.example/fhir/sid/user` | AuditEvent agent | actor id (`system`, `seed`; people use `practitioner-role`) |
| `https://stafeta.example/fhir/sid/service-request` | ServiceRequest | case id |
| `https://stafeta.example/fhir/sid/consent` | Consent | case id |
| `https://stafeta.example/fhir/sid/communication-request` | CommunicationRequest | request task id |
| `https://stafeta.example/fhir/sid/request-task` | report-request Task | `<case id>-req-<n>` |
| `https://stafeta.example/fhir/sid/handover` | Composition (handover) | `<case id>@<as_of UTC YYYYMMDDTHHMMZ>` |
| `https://stafeta.example/fhir/sid/handover-entry` | Condition / MedicationStatement / Observation derived from a handover | `<handover id>#<field key>.<n>` |
| `https://stafeta.example/fhir/sid/device` | Composition.author, Provenance agent (logical Device reference) | `stafeta-handover-ai` |
| `https://ncez.mzcr.cz/fhir/sid/icp` | Organization IČP (CZ Core) | e.g. `72045318` |
| `https://ncez.mzcr.cz/fhir/sid/kp` | Insurer code (CZ Core), Organization + `Coverage.payor.identifier` | `211` |

## Our CodeSystems (`https://stafeta.example/fhir/CodeSystem/<name>`)
| Name | Codes |
| --- | --- |
| `case-state` | odeslano, triage, ceka_na_podklady, kompletni, pripraveno_mdt, zaver_mdt, zpetna_vazba_odeslana, uzavreno (see `contracts/case-states.md`) |
| `task-code` | coordinate-case; step codes of the pancreas pathway: ct-thorax-abdomen, eus-fnb, labs-dx, histology, algesiology, psychooncology, mdt; `request-report` (report requests); `ad-hoc` (single tasks); `result-document` (Task.output type) |
| `pathway-action` | codes of PlanDefinition actions (same values as the step codes). `PlanDefinition.action.participant.role` uses `workflow-role` and mirrors the `owner-role` extension; the mapper reads the extension |
| `audit-type` | domain-event (business-level AuditEvent of a workflow event, payload = ids/states/roles in `entity.detail`) |
| `audit-event-code` | machine event names: submit, accept, request_documents, docs_received, request_report, report_received, … |
| `task-business-status` | objednano, potvrzeno, provedeno, vysledek_dorucen |
| `workflow-role` | gp, coordinator, koc_physician, koc_staff, external_workplace, patient, reviewer, system |
| `organization-kind` | gp_practice, koc, laboratory, outpatient, imaging, insurer |
| `episode-type` | oncology-diagnostics |
| `composition-type` | handover |
| `handover-section` | 1_patient … 15_other (keys shared with `data/golden`) |
| `handover-field-status` | complete, partial, missing, stale, needs_clarification, complete_with_conflict, generated_with_citations |
| `handover-review-state` | draft, confirmed, accepted_missing (used as `valueCode` in the review extension) |
| `provenance-activity` | assemble, extract, confirm, edit, accept-missing, carry-over, waive-readiness |

## Our extensions (`https://stafeta.example/fhir/StructureDefinition/<name>`, not loaded into IRIS)
| Name | On | Value |
| --- | --- | --- |
| `handover-episode` | Composition | valueReference → EpisodeOfCare (Composition.encounter allows Encounter only) |
| `handover-as-of` | Composition | valueDateTime, the cut-off |
| `handover-field-status` | Composition.section | valueCoding `handover-field-status` |
| `handover-conflicts` | Composition.section | valueString, JSON array of the sorted finding ids that contradict the section (`[]` when none); compared by the carry-over (#122) |
| `handover-review` | Composition.section | complex: state (code), by (Reference, PractitionerRole business id), role (code), at (dateTime), edited (boolean), value-hash (string: SHA-256 of the section value the physician confirmed; a later change reopens the review) |
| `handover-edited-value` | Composition.section | valueString, the physician's value as JSON (validated against `contracts/handover.schema.json`) |
| `evidence-quote` | Provenance.entity | complex: quote (string), charStart, charEnd (integer) |
| `handover-section` | Provenance (confirmation) | valueCode, the section key |
| `previous-value-sha256` | Provenance (confirmation) | valueString, SHA-256 of the section value before the confirmation |
| `readiness-item` | Provenance (readiness waiver) | valueCode, the PlanDefinition `mdt-required-items` entry that was waived |
| `tag` | stafeta-demo (all demo writes; wiped by `make demo-reset` except AuditEvents, which are never deleted), stafeta-test (integration tests, cleaned up by the tests) |

## Our extensions (`https://stafeta.example/fhir/StructureDefinition/<name>`)
| Name | On | Value |
| --- | --- | --- |
| `due-rule` | PlanDefinition.action | sub-extensions `anchor` (`start` \| `mdt` \| `action:<id>`), `days`, `workdays` |
| `sla-rule` | PlanDefinition.action | same shape as `due-rule`; the promised turnaround (histology: EUS-FNB + 3 working days) |
| `place` | PlanDefinition.action | workplace as text (on a Task it becomes `Task.location.display`) |
| `owner-role` | PlanDefinition.action | `workflow-role` code of the party responsible for the step |
| `mdt-required-items` | PlanDefinition | sub-extensions `item` (readiness items for the MDT) |
| `depends-on` | Task | `valueString`: business id of a Task that must finish first (repeats) |
| `sla-due` / `escalated-at` | Task | `valueDateTime`: promised deadline / when the overdue escalation fired (once) |
| `ad-hoc` / `demo-assumption` | Task | `valueBoolean` |
| `recorded-on-behalf-by` | Task | `valueReference` (identifier + display): the coordinator who recorded progress for the external workplace that owns the step |
| `mdt-start` | coordinating Task | `valueDateTime`: planned MDT start (anchor of the pathway) |
| `on-behalf-of` | AuditEvent.agent | `valueReference` (display only): the workplace the coordinator recorded a step for. R4 `AuditEvent.agent` has no `onBehalfOf` (Provenance does) |

## Modelling notes and deliberate deviations
- **Deliberate deviations (F2-4).** `Task.executionPeriod.start` holds the *confirmed* date/time of a step that has not
  happened yet (R4 means when it is carried out; an Appointment would be cleaner). `Task.owner` and `Task.location` are
  display/identifier-only References (no PractitionerRole / Location resources in the PoC), so `Task?owner=` does not match.
  `CarePlan` is linked to its case only by the identifier (`CarePlan.encounter` cannot point to an EpisodeOfCare), and the
  step Tasks do not carry `basedOn` → CarePlan. `PlanDefinition` and existence checks (`care_plan_exists`) are read
  without an AuditEvent: they hold no patient data. The ServiceRequest follows its Task: completed → `completed`, cancelled → `revoked` (Task, ServiceRequest and the AuditEvent in one transaction); a failed step keeps it `active`. Only pathway steps and ad-hoc tasks (identifier `case-step`) are read as steps; the other Tasks of a case (report requests) are ignored. Resources and the
  PlanDefinition are validated offline against the R4B structure definitions; the launch Bundle, `If-Match` and the
  lost-race response of a conditional create are covered only by mocks until `pytest -m iris` runs on `make up-local`.
- **Pathway coordination (F2-4).** Steps are found through `Task.partOf` (the coordinating Task), never by `code`, so
  `CaseReader.list_cases` (`code=coordinate-case`) is unaffected. Every read of tasks writes an `AuditEvent`
  (`TaskStore`); every task update writes one `U` AuditEvent whose `outcomeDesc` carries the transition (ids and states
  only; the free-text reason of a fail / cancel lives in `Task.statusReason`). Updates send `If-Match: W/"<versionId>"`; a concurrent change
  answers 409/412 → `409 conflict`. External workplaces do not use Štafeta in the PoC: the coordinator records
  `start`/`performed`/`result_delivered` for them and the audit agent carries the `on-behalf-of` extension.
- **Profiles**: no `meta.profile` is claimed yet. The Patient matches `cz-patient-base` (CZ Core `cz-patient-core`
  requires a RID identifier 1..1, which the documents do not provide).
- **`DocumentReference.date` = received time.** R4 defines it as "when this document reference was created"; we
  create the reference when the KOC receives the report, so it doubles as the received timestamp the as-of rule
  needs. Authored date stays in `content.attachment.creation`.
- **Coordinating Task → case**: `Task.focus` points to the `EpisodeOfCare` because `Task.encounter` only allows
  `Encounter`. Task.status per case state: `requested` (odeslano), `completed` (uzavreno), otherwise `in-progress`;
  EpisodeOfCare.status `active`, `finished` when uzavreno. Suggested for P4 (#2): postponed flag → Task `on-hold` +
  EpisodeOfCare `onhold`; rejected referral → Task `rejected`.
- **References with identifier + display** (`Task.owner`, `EpisodeOfCare.careManager`) carry the PractitionerRole
  business id so readers need no extra lookup.
- **Handover writes audit atomically**: persist and confirm put the AuditEvent into the same transaction Bundle
  (`FhirRepository.transaction(audit_in_bundle=True)`); its entities are the entries' `fullUrl`s, resolved by the
  server. A confirmation PUT always carries `If-Match` (the stored `meta.versionId`); 412 → API 409 `conflict`.
  `ifNoneExist` tokens are URL-encoded (entry identifiers contain `#`). Vital-signs Observations need a numeric
  value and a date; otherwise category `exam` without LOINC.
- **AuditEvent**: `source.observer` is display-only ("Štafeta backend"); `agent.type` uses our `workflow-role`
  (extensible binding → validator warning, accepted); people are identified with the PractitionerRole business id
  (same system as `Task.owner`), technical actors (`system`, `seed`) with `sid/user`. Searches are audited with
  action `E`, reads of identified resources with `R`.
- **Vector index (ADR-0004)**: rows in IRIS SQL `Stafeta.DocChunk` are derived from a DocumentReference. Each
  indexed document is audited with action `C`, subtype `create`, entity = the DocumentReference and `outcomeDesc`
  "Stafeta.DocChunk: N chunks embedded with <model>" (actor `seed` or `vector-index`). Every `/ask` question is
  audited as one read (`R`) of the case Task, the Patient and every DocumentReference whose chunks were retrieved.
  Ask answers are not stored in FHIR: they are display-only drafts ("Návrh AI").
- **No empty arrays**: mappers omit optional lists instead of writing `[]` (FHIR JSON forbids empty arrays).
- **Later**: `doc_id` (file stem) is unique per case, not globally — uploads (F2-1) must scope `ensure` by
  `subject`/case; consider `masterIdentifier` for IHE MHD (#6). RelatedPerson/Coverage identifier values embed the RČ
  (data minimisation, #7). Write + AuditEvent in one transaction Bundle (#9). Our CodeSystems are not loaded into
  IRIS as resources.

## External terminologies
LOINC document types used by the seed: 11488-4 Consult note (01, 05, 12, 13) · 11502-2 Laboratory report (02, 10) ·
18748-4 Diagnostic imaging study (03, 06, 08) · 57133-1 Referral note (04, 07) · 28570-0 Procedure note (09) ·
11526-1 Pathology study (11). Diagnoses ICD-10 (MKN-10), morphology ICD-O-3, relationship v3-RoleCode,
coverage type v3-ActCode, organisation type `http://terminology.hl7.org/CodeSystem/organization-type`.

## Search patterns used (verified on IRIS 2026.1)
- Idempotent create: search `?identifier=<system>|<value>`, then `POST` with `If-None-Exist` (201 created, 200 matched).
- Cases: `Task?code=https://stafeta.example/fhir/CodeSystem/task-code|coordinate-case`.
- Case documents: `DocumentReference?encounter=EpisodeOfCare/<id>`; counts with `_summary=count`.
- Insurer: `Coverage?beneficiary=Patient/<id>&status=active`.
- Demo reset: `<Type>?_tag=https://stafeta.example/fhir/CodeSystem/tag|stafeta-demo`, then `DELETE` per id (dependents
  first, order in `app/seed/loader.py:RESET_ORDER`); AuditEvents are kept, the reset itself is audited.
- As-of: filter `DocumentReference.date` (received) ≤ as_of in the query or in code, and `attachment.creation`
  (authored, not searchable) in code.
- Case read-backs (#131, #113; not yet verified on IRIS): `AuditEvent?entity=Task/<id>&subtype=<audit-event-code>|gp_opened`
  (+ `|reopen`), `Provenance?target=Task/<id>` filtered on activity `waive-readiness` in code (ADR case-waivers).

## Seeded demo data (`python -m app.seed`, scenario `story`)
8 Organization · 17 Practitioner · 17 PractitionerRole · 1 Patient · 1 RelatedPerson · 1 Coverage · 1 EpisodeOfCare ·
1 coordinating Task (`pripraveno_mdt`, owner MDT chair, deadline 2026-10-21T08:00+02:00) · 13 DocumentReference.
Received times are demo assumptions (`backend/app/seed/demo_case.py`); 01–11 before the MDT start, 12–13 after.
Scenario `demo-start` (`make demo-reset`): Organization, Practitioner, PractitionerRole, Patient only.
Deliberately not seeded because the documents do not state them: patient e-mail, GP e-mail, ECOG, TNM.

## Referral intake and report requests (F2-1)
- Extensions (`https://stafeta.example/fhir/StructureDefinition/…`) on the coordinating Task: `baton-role` (code),
  `resume-baton-role` (code), `resume-on` (string), `mdt-start` (dateTime), `conclusion-confirmed`, `delivery-receipt`
  (boolean). Postponed = `Task.status on-hold`; `Task.statusReason.text` = reason of the last transition.
  Other extensions: `consent-statement` (Consent), `prefill-comparison|prefill-edited-fields|prefill-added-fields`
  (Provenance), `request-exam-date` (report-request Task), `reason-evidence` (ServiceRequest: doc id + verbatim quote of the diagnosis, stored only while the GP did not change it).
- External URIs added: ICD-10 `http://hl7.org/fhir/sid/icd-10` (ServiceRequest.reasonCode), `consentscope`, `consentaction`,
  `provenance-participant-type`, `v3-DataOperation`, `v3-ParticipationType`.
- The referral is ONE transaction Bundle (urn:uuid references; entry order is not required by R4 but kept dependency-first for readability). An existing Patient/RelatedPerson/Coverage is found by identifier first and referenced, never overwritten.
  DocumentReferences are plain POSTs (the `source-document` identifier is unique per case, not globally); duplicates are
  detected by identifier + subject. Case Task updates carry `If-Match` (version read). **Not yet verified on IRIS**: `ifMatch` on
  transaction entries and forward-free `urn:uuid` resolution (integration tests `@pytest.mark.iris` exercise them).
- Directory: KOCs are `Organization` with `organization-kind|koc`; the coordinator is the first `PractitionerRole` with
  `workflow-role|coordinator` of that organisation.
