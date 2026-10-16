import json
from datetime import date, datetime
from pathlib import Path
from typing import Any

import pytest

from app.domain import clock
from app.domain.case import Case, CaseState
from app.domain.patient import Patient, Sex

PLAN_PATH = Path(__file__).resolve().parents[4] / "iris" / "fhir" / "plandefinition-pancreas-dx.json"
MDT = datetime(2026, 10, 21, 8, 0, tzinfo=clock.TZ)
PATIENT = Patient(
    given="Alena",
    family="Procházková",
    sex=Sex.FEMALE,
    birth_date=date(1963, 7, 22),
    birth_number="635722/1013",
    insurer_code="211",
)


def make_case(state: CaseState = CaseState.ODESLANO, **kw: Any) -> Case:
    return Case(**{"id": "c1", "patient": PATIENT, "state": state, "mdt_start": MDT, **kw})


def load_plan() -> dict[str, Any]:
    plan: dict[str, Any] = json.loads(PLAN_PATH.read_text(encoding="utf-8"))
    return plan


@pytest.fixture(autouse=True)
def _no_env_clock(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv(clock.ENV_VAR, raising=False)
