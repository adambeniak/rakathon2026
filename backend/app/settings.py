"""Application settings (owner: P1).

Values come from the process environment (`uv run --env-file ../.env …`, docker compose `env_file`). The repo-root
`.env` is read as an optional fallback for local runs. Never hardcode URLs, keys or passwords anywhere else.
Every field has a safe default so the app can be built without any environment (e.g. `make contract` in CI).
"""

from __future__ import annotations

from datetime import datetime
from functools import lru_cache
from pathlib import Path
from zoneinfo import ZoneInfo

from pydantic import AwareDatetime, Field, SecretStr, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

REPO_ROOT = Path(__file__).resolve().parents[2]
PRAGUE = ZoneInfo("Europe/Prague")


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=REPO_ROOT / ".env",
        env_file_encoding="utf-8",
        env_ignore_empty=True,
        extra="ignore",
    )

    stafeta_env: str = Field("local", description="local | ci | azure")
    stafeta_demo_mode: bool = Field(
        True, description="Tag every written FHIR resource with meta.tag stafeta-demo so `--reset` can wipe it."
    )
    stafeta_demo_now: AwareDatetime | None = Field(
        None, description="Simulated 'now' for the demo, e.g. 2026-10-21T08:00:00+02:00."
    )
    stafeta_llm_cache: bool = Field(True, description="1 = use cached LLM responses only (demo/CI).")

    # --- InterSystems IRIS for Health ---
    fhir_base_url: str = "http://localhost:52773/fhir/r4"
    iris_host: str = "localhost"
    iris_superserver_port: int = 1972
    iris_web_port: int = 52773
    iris_namespace: str = "FHIRSERVER"
    iris_user: str = "_SYSTEM"
    iris_password: SecretStr = SecretStr("")
    iris_pool_size: int = Field(3, ge=1, le=3, description="Community edition allows 8 connections in total.")
    http_timeout_s: float = Field(30.0, gt=0)

    # --- Azure APIM gateway (OpenAI-compatible); used by app.extraction ---
    apim_base_url: str = ""
    apim_api_key: SecretStr = SecretStr("")
    llm_model_extract: str = ""
    llm_model_fast: str = ""
    embedding_model: str = ""

    # --- App ---
    jwt_secret: SecretStr = SecretStr("change-me-local-only")
    smtp_host: str = "localhost"
    smtp_port: int = 1025
    cors_origins: list[str] = Field(default_factory=lambda: ["http://localhost:5173"])
    log_level: str = "INFO"
    log_json: bool = True

    @field_validator("fhir_base_url")
    @classmethod
    def _strip_trailing_slash(cls, value: str) -> str:
        return value.rstrip("/")

    def now(self) -> datetime:
        """Demo-aware current time in Europe/Prague (P4 replaces this with `app.domain.clock` in #2/#3)."""
        if self.stafeta_demo_now is not None:
            return self.stafeta_demo_now.astimezone(PRAGUE)
        return datetime.now(PRAGUE)


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings()
