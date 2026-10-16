"""Outbound notifications and delivery proof: e-mail via SMTP (mailpit in the demo), read receipts (owner: P4).

Every delivery and read receipt is recorded as `Communication` + `AuditEvent` through `app.fhir.repository`.
"""
