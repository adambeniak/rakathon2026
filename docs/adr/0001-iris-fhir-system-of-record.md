# ADR-0001: IRIS for Health FHIR R4 is the system of record; the domain model lives in the backend

- Date: 2026-10-16 · Status: accepted · Owner: P1 (architect)

## Context
- The challenge is about losing information between GP, KOC, MDT and back; hospitals exchange data via FHIR/HL7.
- InterSystems IRIS for Health gives us a FHIR R4 repository, HL7 v2 → FHIR interoperability, SQL and vector search
  in one container (team ACI, 2 GB RAM, 8 connections, non-persistent storage).
- Four people build in parallel tonight; UI and logic need small, typed, stable shapes, not raw FHIR JSON.
- Demo resets and E2E tests must not depend on server-generated ids.

## Decision
1. All clinical and workflow data is stored as FHIR R4 resources in IRIS (`/fhir/r4`, namespace FHIRSERVER).
   No second database for clinical data; IRIS SQL is used only for derived data (vector chunks, analytics).
2. The backend has an internal domain model (`backend/app/domain`, Pydantic). Mapping domain ↔ FHIR happens only in
   `backend/app/fhir/mappers`. API schemas are separate Pydantic models; contracts are generated from code.
3. Every write goes through `backend/app/fhir/repository.py`, which stamps the demo tag (demo mode) and writes an
   `AuditEvent`; reads of clinical content are audited explicitly.
4. **API ids are business identifiers, never FHIR logical ids**: case `rakathon-2026-prochazkova`, document
   `doc_id` = file stem. Every resource the API exposes carries an identifier under
   `https://stafeta.example/fhir/sid/<kind>`, which also makes creates idempotent (`If-None-Exist`).
5. Case = `EpisodeOfCare` + coordinating `Task` (state in `businessStatus`, baton holder in `owner`).

## Consequences
- Easier: interoperability story, audit and provenance for free in FHIR terms, parallel work against stable
  contracts, idempotent seed/reset, stable URLs across `make demo-reset`.
- Harder: every new concept needs a mapper and a row in `docs/fhir-mapping.md`; reads need several FHIR calls
  (watch latency on ACI, use `_include`/`_summary=count` where IRIS supports it).
- Watch: write + AuditEvent are two calls (not atomic); IRIS restarts lose data (bootstrap + seed); RČ already uses the
  CZ Core system (`https://ncez.mzcr.cz/fhir/sid/rcis`); the demo `stafeta.example` systems must be replaced or
  registered before a pilot.
