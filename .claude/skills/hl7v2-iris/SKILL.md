---
name: hl7v2-iris
description: How Štafeta ingests HL7 v2 messages (lab results ORU^R01, documents MDM^T02) and turns them into FHIR R4 in InterSystems IRIS for Health — the IRIS-native production path (HL7 service → HL7ToSDA3 → SDA3→FHIR → FHIR repository) and the Python fallback. Use when building or testing the HL7 v2 interoperability feature or writing sample messages.
---
# HL7 v2 → FHIR in IRIS

## Why
Hospitals' lab and document systems still speak HL7 v2. Showing that a lab result arriving as HL7 v2 lands as a
FHIR Observation in the shared case (and appears in the handover with evidence) is our interoperability proof.

## Path A — IRIS native (preferred for the InterSystems challenge)
Built-in components (verify class names in your IRIS version):
1. Business Service: `EnsLib.HL7.Service.HTTPService` (or `TCPService` for MLLP, `FileService` for a drop folder).
2. Business Process: custom 3-line BP calling `##class(HS.Gateway.HL7.HL7ToSDA3).GetSDA(pRequest,.tSDA)` and sending
   `##class(Ens.StreamContainer).%New(tSDA)` onward.
3. Business Process: `HS.FHIR.DTL.Util.HC.SDA3.FHIR.Process` with `FHIRMetadataSet = HL7v40`,
   `TransmissionMode = transaction`, `FHIREndpoint = /fhir/r4`.
4. Business Operation: `HS.FHIRServer.Interop.Operation` (local repository).
Reference implementation: github.com/grongierisc/iris-healthtoolkit-service (`FoundationProduction.cls`).
The production class lives in `iris/src/Stafeta/Production.cls`; load + start it from `scripts/bootstrap_iris.py`
(must be re-applied after every ACI restart). MDM^T02 → DocumentReference via SDA is UNVERIFIED — test first.

## Path B — fallback in the backend (if Path A is not working by the agreed deadline)
`backend/app/integration/hl7v2.py`: parse with the `hl7` Python package, map OBX → `Observation` (LOINC from a
small local map), OBR → `DiagnosticReport`, and POST a transaction Bundle to IRIS. Expose `POST /api/hl7v2`.
Be honest in the pitch about which path the demo uses.

## Sample ORU^R01 for the demo (fictitious, matches report 10)
```text
MSH|^~\&|LIS|KOC2_LIPOVA|STAFETA|KOC2|20261015074500||ORU^R01|MSG0001|P|2.5.1
PID|1||635722/1013^^^RC^NI||Procházková^Alena||19630722|F
OBR|1||LAB-20261015-01|24108-3^CA 19-9^LN|||20261015074500
OBX|1|NM|24108-3^Cancer Ag 19-9^LN||312|kU/L|<37|H|||F
OBX|2|NM|2039-6^CEA^LN||4.1|ug/L|<5.0|N|||F
OBX|3|NM|10334-1^Cancer Ag 125^LN||48|kU/L|<35|H|||F
```
Keep segment separators as `\r` when sending. Post with `Content-Type: application/hl7-v2`.

## Test
`make hl7-demo` (to be added) sends the sample message and asserts that `Observation?code=http://loinc.org|24108-3`
returns value 312 kU/L for the patient, with a Provenance pointing at the HL7 message.
