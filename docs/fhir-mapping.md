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
| Referral (žádost PL) | `ServiceRequest` | intent order, priority urgent, requester GP, performer KOC, reasonCode C25.0 (suspected), supportingInfo → DocumentReference | F2-1 |
| Step (`domain.task.Task`) | `Task` partOf case Task | owner, `restriction.period.end` = due, `businessStatus` (`task-business-status`), location, dependencies | F2-4 |
| Pathway template | `PlanDefinition` → `CarePlan` | "Karcinom pankreatu – diagnostika", relatedAction before/after | F1-4 / F2-4 |
| Lab result | `Observation` (LOINC) in `DiagnosticReport` | effectiveDateTime = collection time | F2/F3-5 |
| Diagnosis | `Condition` (mCODE PrimaryCancerCondition idea) | ICD-10 C25.0, verificationStatus provisional → confirmed, morphology 8500/3 | F2-2 |
| Handover / MDT record | `Composition` (preliminary → final) | sections = 15 handover fields / MDT_zapis; attester = confirming physician | F2-2 / F3-3 |
| AI evidence / confirmation | `Provenance` | target = derived resource, entity.what = source DocumentReference, quote in extension, agent = model (Device) + confirming Practitioner | F2-2 |
| Consent / wishes | `Consent` | sharing with the daughter | F2-1 |
| Messages | `CommunicationRequest` / `Communication` | request missing reports; MDT result to GP; `received` = delivery proof | F2-1 / F3-4 |

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
| `https://stafeta.example/fhir/sid/source-document` | DocumentReference | file stem (= `doc_id` in evidence) |
| `https://stafeta.example/fhir/sid/user` | AuditEvent agent | actor id (`system`, `seed`, later the user's role id) |
| `https://ncez.mzcr.cz/fhir/sid/icp` | Organization IČP (CZ Core) | e.g. `72045318` |
| `https://ncez.mzcr.cz/fhir/sid/kp` | Insurer code (CZ Core), Organization + `Coverage.payor.identifier` | `211` |

## Our CodeSystems (`https://stafeta.example/fhir/CodeSystem/<name>`)
| Name | Codes |
| --- | --- |
| `case-state` | odeslano, triage, ceka_na_podklady, kompletni, pripraveno_mdt, zaver_mdt, zpetna_vazba_odeslana, uzavreno (see `contracts/case-states.md`) |
| `task-code` | coordinate-case (F2-4 adds step codes) |
| `task-business-status` | objednano, potvrzeno, provedeno, vysledek_dorucen |
| `workflow-role` | gp, coordinator, koc_physician, koc_staff, external_workplace, patient, reviewer, system |
| `organization-kind` | gp_practice, koc, laboratory, outpatient, imaging, insurer |
| `episode-type` | oncology-diagnostics |
| `tag` | stafeta-demo (all demo writes; wiped by `make demo-reset` except AuditEvents, which are never deleted), stafeta-test (integration tests, cleaned up by the tests) |

## Modelling notes and deliberate deviations
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
- **AuditEvent**: `source.observer` is display-only ("Štafeta backend"); `agent.type` uses our `workflow-role`
  (extensible binding → validator warning, accepted); people are identified with the PractitionerRole business id
  (same system as `Task.owner`), technical actors (`system`, `seed`) with `sid/user`. Searches are audited with
  action `E`, reads of identified resources with `R`.
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

## Seeded demo data (`python -m app.seed`, scenario `story`)
8 Organization · 17 Practitioner · 17 PractitionerRole · 1 Patient · 1 RelatedPerson · 1 Coverage · 1 EpisodeOfCare ·
1 coordinating Task (`pripraveno_mdt`, owner MDT chair, deadline 2026-10-21T08:00+02:00) · 13 DocumentReference.
Received times are demo assumptions (`backend/app/seed/demo_case.py`); 01–11 before the MDT start, 12–13 after.
Scenario `demo-start` (`make demo-reset`): Organization, Practitioner, PractitionerRole, Patient only.
Deliberately not seeded because the documents do not state them: patient e-mail, GP e-mail, ECOG, TNM.
