<!-- WHO: P1 · TOOL: Claude Code Opus 5.5 xhigh + iris-integration subagent · MODE: PLAN · WHEN: F3 (00:00–04:00), STRETCH — timebox 2 h, then fall back to Path B -->

ROLE: InterSystems interoperability engineer.

CONTEXT: Read the hl7v2-iris skill (Path A native production, Path B Python fallback), the iris-integration subagent,
scripts/bootstrap_iris.py. The shared IRIS is non-persistent: the production must be (re)created by the bootstrap.

GOAL: A lab result sent as HL7 v2 ORU^R01 lands in the FHIR repository as Observations linked to the patient, appears
in the case (Laboratoř section, with evidence = the HL7 message) and is visible in the IRIS production message viewer.

PLAN FIRST: decide Path A vs B after a 20-minute spike: can you load + compile an ObjectScript production class and
start it remotely via the Native API (e.g. `%Compiler.UDL.TextServices` / `$System.OBJ.Load` of a stream) on our
image? Show the evidence, then plan.

BUILD (Path A)
1. `iris/src/Stafeta/Production.cls` (HL7 HTTP service → HL7ToSDA3 BP → SDA3→FHIR process (HL7v40, transaction,
   /fhir/r4) → FHIR operation) + the 3-line BP class; bootstrap loads, compiles, configures and starts it idempotently.
2. `make hl7-demo` posts `iris/hl7v2/samples/oru_r01_koc2_20261015.hl7` and asserts the Observation exists.
3. Backend picks up new Observations for the case (poll `_lastUpdated` every 30 s in demo mode — IRIS FHIR
   subscriptions are not confirmed) and records Provenance (entity = HL7 message control ID).
BUILD (Path B) — as described in the skill, `POST /api/hl7v2`.

ACCEPTANCE
- [ ] Sending the sample message creates CA 19-9 = 312 kU/L (LOINC 24108-3) for the patient
- [ ] Screenshot of the IRIS Interoperability message trace for the pitch (Path A) — or an honest note (Path B)
- [ ] `docs/interoperability.md` describes the flow and the production path (MLLP/TCP, TLS, real LIS)
