from __future__ import annotations

import pytest
from pydantic import SecretStr, ValidationError

from app.settings import Settings


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
