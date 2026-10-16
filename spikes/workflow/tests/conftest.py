from datetime import datetime
from pathlib import Path

import pytest

from domain import clock

ROOT = Path(__file__).resolve().parents[3]
PLAN_PATH = ROOT / "iris" / "fhir" / "plandefinition-pancreas-dx.json"
MDT = datetime(2026, 10, 21, 8, 0, tzinfo=clock.TZ)


@pytest.fixture(autouse=True)
def _no_env_clock(monkeypatch):
    monkeypatch.delenv(clock.ENV_VAR, raising=False)
