---
name: fhir-iris
description: Project-specific guide for talking to the Štafeta FHIR R4 server on InterSystems IRIS for Health (local docker or team ACI) — base URL, auth, bootstrap, the domain-to-FHIR mapping of the oncology case (EpisodeOfCare, Task, CarePlan, DocumentReference, Composition, Provenance, Consent, Communication, AuditEvent), search patterns, transaction bundles, vector search table and known IRIS gotchas. Use for any code that reads or writes FHIR or IRIS SQL in this repo.
---
# FHIR on IRIS — Štafeta specifics

The generic kit skills (`kit-iris-fhir`, `kit-iris-sql-python`, `kit-iris-vector-search`, `kit-iris-environment`,
MIT, from FHIR-AI-Hackathon-Kit) use `localhost` + `SuperUser/SYS`. **In this repo** use env vars instead:

| Thing | Value |
| --- | --- |
| FHIR base | `$FHIR_BASE_URL` (default `http://localhost:52773/fhir/r4`; inside docker compose `http://iris:52773/fhir/r4`), namespace `FHIRSERVER` |
| Auth | HTTP Basic `$IRIS_USER` / `$IRIS_PASSWORD` (`_SYSTEM` + password file in ACI) |
| SQL / Native API | `iris.connect($IRIS_HOST, 1972, "FHIRSERVER", user, pw)` (`intersystems-irispython==5.4.1`) |
| Bootstrap | `make iris-bootstrap` (namespace, FHIR endpoint JsonAdvSQL, `Stafeta.DocChunk` vector table) |
| Swagger | `http://<host>:52773/fhir/swagger-ui/index.html` only if created; Management Portal `/csp/sys/%25CSP.Portal.Home.zen` |

## Case model (keep `docs/fhir-mapping.md` as the full table)
| Domain concept | FHIR R4 | Key elements |
| --- | --- | --- |
| Patient | `Patient` (+ `RelatedPerson` daughter) | identifier RČ (system from CZ Core if available), name, gender, birthDate, telecom, address |
| Insurance | `Coverage` → payor `Organization` (code 211) | |
| KOC / workplace directory | `Organization`, `PractitionerRole`, `Endpoint` (mCSD-like) | KOC 1, KOC 2, GP practice |
| Referral (žádost PL) | `ServiceRequest` (intent `order`, priority `urgent`) | requester GP, performer KOC 2, reasonCode C25.0 (suspected), supportingInfo → DocumentReference |
| Case | `EpisodeOfCare` + coordinating `Task` | Task.code `coordinate-case`, Task.businessStatus = case state (CodeSystem `case-state`: odeslano, triage, ceka_na_podklady, kompletni, pripraveno_mdt, zaver_mdt, zpetna_vazba_odeslana, uzavreno), Task.owner = who holds the baton |
| Step | `Task` partOf case Task | owner, `restriction.period.end` = due, `businessStatus` (objednano, potvrzeno, provedeno, vysledek_dorucen), location via `Task.location`, dependencies via extension or `Task.basedOn` order |
| Pathway template | `PlanDefinition` → instantiated `CarePlan` | "Karcinom pankreatu – diagnostika" actions with `relatedAction` (before/after) |
| Source document | `DocumentReference` | `date` = received, `content.attachment.creation` = authored, `type` LOINC, `custodian` workplace, attachment **base64** (the kit's notes use hex — do not copy that) |
| Lab result | `Observation` (LOINC) inside `DiagnosticReport` | effectiveDateTime = collection time |
| Diagnosis | `Condition` (mCODE PrimaryCancerCondition idea) | ICD-10 C25.0, verificationStatus provisional → confirmed after histology; morphology 8500/3 |
| Handover / MDT record | `Composition` (status preliminary → final) | sections mirror Handover_obsah / MDT_zapis; `attester` = confirming physician |
| AI evidence | `Provenance` | target = derived resource, entity.what = source DocumentReference, entity extension = verbatim quote, agent = model (Device) + confirming Practitioner |
| Consent / wishes | `Consent` | sharing with daughter |
| Messages | `CommunicationRequest` (ask for missing report) / `Communication` (MDT result to GP, reviewer) | `received` timestamp = delivery proof |
| Audit | `AuditEvent` | every write, every read of clinical content, delivery and read receipts |

## Patterns
- Writes that belong together → **transaction Bundle** with `urn:uuid:` fullUrls (POST to base URL).
- Idempotency → conditional create `ifNoneExist: "identifier=<system>|<value>"` or conditional `PUT Resource?identifier=...`.
- As-of queries → filter DocumentReference by `date=le<asOf>` AND attachment.creation ≤ asOf in code (creation is not searchable).
- Search: use `family`/`given` (not `name` with a space); unknown params are silently ignored — always check results.
- Everything for a patient: `GET Patient/{id}/$everything`.
- Validation errors come back as 400 with an `OperationOutcome` — surface its `issue[].diagnostics` in logs (no PHI).

## IRIS gotchas
- Community edition: **8 connections**. Use one small pool in the backend; always close cursor then connection.
- No `DESCRIBE`; use `INFORMATION_SCHEMA`. Use `TOP n` (LIMIT/OFFSET only in 2025.1+). Check version with `$zv`.
- Vector search: `VECTOR(DOUBLE, 384)`, insert with `TO_VECTOR(?, DOUBLE)`, query
  `SELECT TOP 5 DocRef, Text FROM Stafeta.DocChunk WHERE PatientRef = ? ORDER BY VECTOR_COSINE(Embedding, TO_VECTOR(?, DOUBLE)) DESC`.
  Embeddings are computed in the backend (APIM embedding model if available, else local multilingual model) —
  never run sentence-transformers inside the 2 GB container.
- ACI storage is not persistent: after any restart run `make iris-bootstrap && make seed`.
- Do not enable FHIR `DebugMode` that accepts unauthenticated requests — the ACI ports are public.
