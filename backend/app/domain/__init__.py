"""Internal domain model: pure Pydantic models and (later) pure logic, no I/O (owner: P4; models by P1).

Never import FastAPI, httpx, FHIR JSON or adapters here. FHIR mapping lives only in `app.fhir.mappers`.
State machines: case (#2) and task (#3) are added by P4 as new modules (case_machine.py, task_machine.py).
"""
