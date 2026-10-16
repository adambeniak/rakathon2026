"""FHIR R4 adapter for InterSystems IRIS for Health (owner: P1).

`client` speaks HTTP, `repository` adds the demo tag and an `AuditEvent` for every write, `mappers` translate
domain models <-> FHIR JSON. Nothing outside this package should build or parse FHIR JSON.
"""
