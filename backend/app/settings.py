"""Application settings (owner: P1).

Values come from the process environment (`uv run --env-file ../.env …`, docker compose `env_file`). The repo-root
`.env` is read as an optional fallback for local runs. Never hardcode URLs, keys or passwords anywhere else.
Every field has a safe default so the app can be built without any environment (e.g. `make contract` in CI).
"""

from __future__ import annotations

from datetime import datetime
from functools import lru_cache
from pathlib import Path
from typing import Literal
from zoneinfo import ZoneInfo

from pydantic import AwareDatetime, Field, SecretStr, field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

from app.domain import clock

REPO_ROOT = Path(__file__).resolve().parents[2]
PRAGUE = ZoneInfo("Europe/Prague")
DEV_ENVS = frozenset({"local", "ci", "test"})
DEFAULT_JWT_SECRET = "change-me-local-only"  # noqa: S105 - refused outside DEV_ENVS


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=REPO_ROOT / ".env",
        env_file_encoding="utf-8",
        env_ignore_empty=True,
        extra="ignore",
    )

    stafeta_env: str = Field("local", description="local | ci | azure")
    stafeta_demo_mode: bool = Field(
        False,
        description="STAFETA_DEMO_MODE=1: honour the X-Demo-Role mock login (default coordinator) and tag every "
        "written FHIR resource with meta.tag stafeta-demo so `--reset` can wipe it. "
        "Off = every request is 401 (fail closed).",
    )
    stafeta_demo_now: AwareDatetime | None = Field(
        None, description="Simulated 'now' for the demo, e.g. 2026-10-21T08:00:00+02:00."
    )
    stafeta_watchdog_enabled: bool | None = Field(
        None, description="SLA watchdog loop; unset = on in demo mode, off otherwise."
    )
    stafeta_watchdog_interval_s: float = Field(60.0, gt=0, description="Seconds between watchdog runs.")
    stafeta_llm_cache: bool = Field(True, description="1 = use cached LLM responses only (demo/CI).")
    handover_stale_vitals_days: int = Field(
        30, ge=1, description="DEMO RULE: weight older than this at as_of is reported as stale in the handover."
    )

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
    embedding_model: str = Field("", description="APIM embedding deployment; used when EMBEDDING_PROVIDER=apim.")

    # --- Vector search and "ask the case" (app.retrieval, docs/vector-search.md) ---
    embedding_provider: Literal["local", "apim"] = Field(
        "local", description="local = fastembed ONNX on the backend CPU; apim = EMBEDDING_MODEL via APIM."
    )
    local_embedding_model: str = "sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2"
    embedding_dim: int = Field(384, description="Must equal VECTOR(DOUBLE, n) of Stafeta.DocChunk (bootstrap).")
    fastembed_cache_path: Path = Field(
        REPO_ROOT / "backend" / ".cache" / "fastembed", description="Model files; baked into the Docker image."
    )
    ask_top_k: int = Field(10, ge=1, le=20, description="Chunks retrieved per question.")

    # --- App ---
    upload_max_bytes: int = Field(
        10 * 1024 * 1024, ge=1024, description="Largest accepted uploaded file; checked before the body is parsed."
    )
    jwt_secret: SecretStr = SecretStr(DEFAULT_JWT_SECRET)
    smtp_host: str = "localhost"
    smtp_port: int = 1025
    cors_origins: list[str] = Field(default_factory=lambda: ["http://localhost:5173"])
    log_level: str = "INFO"
    log_json: bool = True

    @field_validator("fhir_base_url")
    @classmethod
    def _strip_trailing_slash(cls, value: str) -> str:
        return value.rstrip("/")

    @model_validator(mode="after")
    def _safe_outside_local(self) -> Settings:
        """Refuse development defaults when deployed (STAFETA_ENV other than local/ci/test)."""
        if self.stafeta_env in DEV_ENVS:
            return self
        if self.jwt_secret.get_secret_value() == DEFAULT_JWT_SECRET:
            raise ValueError("JWT_SECRET must be set outside local development")
        if "*" in self.cors_origins:
            raise ValueError("CORS_ORIGINS must list explicit origins outside local development")
        return self

    @property
    def watchdog_enabled(self) -> bool:
        return self.stafeta_demo_mode if self.stafeta_watchdog_enabled is None else self.stafeta_watchdog_enabled

    def now(self) -> datetime:
        """Demo-aware current time in Europe/Prague. The one clock is `app.domain.clock`; `STAFETA_DEMO_NOW` is its
        start value and `PUT /api/demo/clock` moves it."""
        if self.stafeta_demo_now is not None and not clock.is_overridden():
            return self.stafeta_demo_now.astimezone(PRAGUE)
        return clock.now().astimezone(PRAGUE)


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings()
