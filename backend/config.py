"""SCL-Governor configuration via pydantic-settings.

All values can be overridden through environment variables (case-insensitive)
or a `.env` file located alongside this module.
"""

from __future__ import annotations

from functools import lru_cache

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Central configuration for the SCL-Governor application."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    # ── Application ──────────────────────────────────────────────────────
    APP_NAME: str = "SCL-Governor"
    APP_VERSION: str = "1.0.0"
    DEBUG: bool = False

    # ── Control loop ─────────────────────────────────────────────────────
    CONTROL_CYCLE_INTERVAL: int = Field(
        default=15,
        ge=1,
        le=60,
        description="Seconds between control cycles",
    )

    # ── Infrastructure endpoints ─────────────────────────────────────────
    PROMETHEUS_URL: str = "http://prometheus:9090"
    REDIS_URL: str = "redis://redis:6379/0"

    # ── Kubernetes ───────────────────────────────────────────────────────
    KUBERNETES_IN_CLUSTER: bool = False
    KUBERNETES_KUBECONFIG: str | None = None

    # ── LLM provider ────────────────────────────────────────────────────
    LLM_PROVIDER: str = Field(
        default="anthropic",
        pattern="^(anthropic|openai)$",
        description="LLM backend to use: 'anthropic' or 'openai'",
    )
    LLM_MODEL: str = "claude-sonnet-4-20250514"
    ANTHROPIC_API_KEY: str = ""
    OPENAI_API_KEY: str = ""

    # ── Simulation ───────────────────────────────────────────────────────
    SIMULATION_SCENARIOS: int = 100
    PREDICTION_HORIZONS: list[int] = [300, 900, 3600]

    # ── Confidence thresholds ────────────────────────────────────────────
    CONFIDENCE_THRESHOLD_HIGH: float = 0.85
    CONFIDENCE_THRESHOLD_MEDIUM: float = 0.65
    CONFIDENCE_THRESHOLD_LOW: float = 0.40

    # ── Safety guardrails ────────────────────────────────────────────────
    MAX_BLAST_RADIUS: float = Field(
        default=0.25,
        ge=0.0,
        le=1.0,
        description="Maximum fraction of traffic an action may affect",
    )
    MAX_SCALE_PER_MINUTE: int = 5
    COOLDOWN_SECONDS: int = 120

    # ── YAML config paths ────────────────────────────────────────────────
    SAFETY_CONFIG_PATH: str = "../config/safety-constraints.yaml"
    REGIME_CONFIG_PATH: str = "../config/regime-profiles.yaml"
    ACTION_CATALOG_PATH: str = "../config/action-catalog.yaml"
    SCL_CONFIG_PATH: str = "../config/scl-config.yaml"

    # ── Notifications ────────────────────────────────────────────────────
    SLACK_WEBHOOK_URL: str = ""
    PAGERDUTY_API_KEY: str = ""

    # ── CORS ─────────────────────────────────────────────────────────────
    CORS_ORIGINS: list[str] = [
        "http://localhost:3000",
        "http://localhost:5173",
    ]


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    """Return a cached singleton of the application settings."""
    return Settings()
