from __future__ import annotations

import pytest
from pydantic import SecretStr, ValidationError

from app.settings import Settings


@pytest.fixture(autouse=True)
def _isolated_env(monkeypatch: pytest.MonkeyPatch) -> None:
    """The process environment overrides constructor defaults; keep these tests independent of a loaded env file."""
    for name in ("STAFETA_ENV", "JWT_SECRET", "CORS_ORIGINS", "FHIR_BASE_URL"):
        monkeypatch.delenv(name, raising=False)


def test_dev_defaults_are_accepted_locally() -> None:
    settings = Settings(_env_file=None, stafeta_env="local")
    assert settings.fhir_base_url == "http://localhost:52773/fhir/r4"


def test_deployed_env_refuses_default_jwt_secret() -> None:
    with pytest.raises(ValidationError, match="JWT_SECRET"):
        Settings(_env_file=None, stafeta_env="azure")


def test_deployed_env_refuses_wildcard_cors() -> None:
    with pytest.raises(ValidationError, match="CORS_ORIGINS"):
        Settings(_env_file=None, stafeta_env="azure", jwt_secret=SecretStr("s3cret-from-key-vault"), cors_origins=["*"])


def test_trailing_slash_is_stripped() -> None:
    assert Settings(_env_file=None, fhir_base_url="http://iris:52773/fhir/r4/").fhir_base_url.endswith("/r4")


def test_settings_now_follows_the_domain_clock() -> None:
    from datetime import datetime

    from app.domain import clock

    settings = Settings(_env_file=None, stafeta_demo_now="2026-10-02T09:00:00+02:00")
    assert settings.now() == datetime(2026, 10, 2, 9, 0, tzinfo=clock.TZ)
    try:
        clock.set_override(datetime.fromisoformat("2026-10-16T09:00:00"))
        assert settings.now() == datetime(2026, 10, 16, 9, 0, tzinfo=clock.TZ)
    finally:
        clock.set_override(None)
    assert settings.now() == datetime(2026, 10, 2, 9, 0, tzinfo=clock.TZ)
