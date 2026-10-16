---
applyTo: "iris/**,backend/app/fhir/**,backend/app/iris/**,scripts/*iris*"
---
Follow `.claude/rules/fhir.md` and `docs/fhir-mapping.md`. Critical points:
- FHIR R4; mapping only in `backend/app/fhir/mappers/`; update `docs/fhir-mapping.md` in the same PR.
- Idempotent writes (conditional create, identifiers); transaction Bundles for multi-resource writes.
- IRIS on ACI is not persistent: everything must be recreatable with `make iris-bootstrap && make seed`.
