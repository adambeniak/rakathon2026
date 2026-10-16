---
paths:
  - "iris/**"
  - "backend/app/fhir/**"
  - "backend/app/iris/**"
  - "scripts/*iris*"
---
# FHIR / IRIS rules
- FHIR R4 only. Map domain ↔ FHIR exclusively in `backend/app/fhir/mappers/`. Keep `docs/fhir-mapping.md` in sync in the same PR.
- Use conditional create/update (`If-None-Exist`, identifiers) so seeding and bootstrap are idempotent.
- Use transaction Bundles for multi-resource writes that must succeed together (e.g. DocumentReference + Provenance + AuditEvent).
- Identifiers: stable `system` URIs; demo-only systems live under `https://stafeta.example/fhir/sid/`.
- Terminologies: LOINC (labs, documents), MKN-10/ICD-10 (diagnoses), ICD-O-3 (morphology), our CodeSystems for case/task states.
- IRIS on ACI loses data on restart: everything must be recreatable by `make iris-bootstrap && make seed`.
- Ask the `fhir-architect` subagent to review new mappings; use the `fhir-iris` skill for endpoints and auth.
