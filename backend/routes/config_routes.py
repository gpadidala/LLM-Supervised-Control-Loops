"""Configuration API routes.

Endpoints for viewing and updating runtime configuration, safety constraints,
and confidence thresholds.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from config import get_settings
from core.shared import get_governor
from utils.logger import get_logger

router = APIRouter(prefix="/config", tags=["config"])
log = get_logger(__name__)

# ── Cached YAML configurations ──────────────────────────────────────────
_yaml_cache: dict[str, Any] = {}


def _load_yaml(path: str) -> dict[str, Any]:
    """Load a YAML file and cache the result. Return empty dict on error."""
    if path in _yaml_cache:
        return _yaml_cache[path]

    p = Path(path)
    if not p.exists():
        log.warning("yaml_not_found", path=path)
        _yaml_cache[path] = {}
        return {}

    try:
        with p.open("r", encoding="utf-8") as fh:
            data = yaml.safe_load(fh) or {}
    except Exception as exc:
        log.error("yaml_load_error", path=path, error=str(exc))
        _yaml_cache[path] = {}
        return {}

    _yaml_cache[path] = data
    log.info("yaml_loaded", path=path)
    return data


def reload_yaml_configs() -> None:
    """Force-reload all YAML configs from disk."""
    settings = get_settings()
    _yaml_cache.clear()
    _load_yaml(settings.SAFETY_CONFIG_PATH)
    _load_yaml(settings.REGIME_CONFIG_PATH)
    _load_yaml(settings.ACTION_CATALOG_PATH)
    _load_yaml(settings.SCL_CONFIG_PATH)
    log.info("yaml_configs_reloaded")


# ── Request models ──────────────────────────────────────────────────────


class WeightsUpdate(BaseModel):
    """Update objective function weights."""

    performance: float | None = Field(default=None, ge=0.0, le=1.0)
    cost: float | None = Field(default=None, ge=0.0, le=1.0)
    risk: float | None = Field(default=None, ge=0.0, le=1.0)
    stability: float | None = Field(default=None, ge=0.0, le=1.0)
    business: float | None = Field(default=None, ge=0.0, le=1.0)


class ThresholdsUpdate(BaseModel):
    """Update confidence thresholds."""

    high: float | None = Field(default=None, ge=0.0, le=1.0)
    medium: float | None = Field(default=None, ge=0.0, le=1.0)
    low: float | None = Field(default=None, ge=0.0, le=1.0)


class SafetyUpdate(BaseModel):
    """Update safety constraints."""

    max_blast_radius: float | None = Field(default=None, ge=0.0, le=1.0)
    max_scale_per_minute: int | None = Field(default=None, ge=1, le=50)
    cooldown_seconds: int | None = Field(default=None, ge=10, le=3600)


# ── Endpoints ───────────────────────────────────────────────────────────


@router.get("/")
async def get_current_config() -> dict[str, Any]:
    """Return the current SCL configuration (secrets redacted)."""
    settings = get_settings()
    data = settings.model_dump()
    # Redact secrets
    for key in (
        "ANTHROPIC_API_KEY",
        "OPENAI_API_KEY",
        "PAGERDUTY_API_KEY",
        "SLACK_WEBHOOK_URL",
    ):
        if data.get(key):
            data[key] = "***REDACTED***"
    return data


@router.put("/weights")
async def update_weights(req: WeightsUpdate) -> dict[str, Any]:
    """Update objective function weights.

    Updates are stored in the SCL YAML config.  The sum of all weights
    should ideally equal 1.0, but this is not enforced -- the simulation
    phase normalises weights internally.
    """
    settings = get_settings()
    scl_config = _load_yaml(settings.SCL_CONFIG_PATH)

    weights = scl_config.setdefault("objective_weights", {})
    if req.performance is not None:
        weights["performance"] = req.performance
    if req.cost is not None:
        weights["cost"] = req.cost
    if req.risk is not None:
        weights["risk"] = req.risk
    if req.stability is not None:
        weights["stability"] = req.stability
    if req.business is not None:
        weights["business"] = req.business

    # Persist to YAML
    _save_yaml(settings.SCL_CONFIG_PATH, scl_config)

    log.info("objective_weights_updated", weights=weights)
    return {"status": "updated", "weights": weights}


@router.put("/thresholds")
async def update_thresholds(req: ThresholdsUpdate) -> dict[str, Any]:
    """Update confidence thresholds for autonomy level gating."""
    settings = get_settings()

    updated: dict[str, float] = {}
    if req.high is not None:
        # We can't modify the cached Settings (it's frozen), but we can
        # update the YAML config which is re-read by the governor.
        updated["high"] = req.high
    if req.medium is not None:
        updated["medium"] = req.medium
    if req.low is not None:
        updated["low"] = req.low

    scl_config = _load_yaml(settings.SCL_CONFIG_PATH)
    scl_config.setdefault("confidence_thresholds", {}).update(updated)
    _save_yaml(settings.SCL_CONFIG_PATH, scl_config)

    log.info("confidence_thresholds_updated", thresholds=updated)
    return {"status": "updated", "thresholds": scl_config.get("confidence_thresholds", {})}


@router.get("/safety")
async def get_safety_constraints() -> dict[str, Any]:
    """Return the current safety constraints."""
    settings = get_settings()
    yaml_safety = _load_yaml(settings.SAFETY_CONFIG_PATH)

    return {
        "max_blast_radius": settings.MAX_BLAST_RADIUS,
        "max_scale_per_minute": settings.MAX_SCALE_PER_MINUTE,
        "cooldown_seconds": settings.COOLDOWN_SECONDS,
        "yaml_config": yaml_safety,
    }


@router.put("/safety")
async def update_safety_constraints(req: SafetyUpdate) -> dict[str, Any]:
    """Update safety constraints (with validation).

    Updates are written to the safety YAML config.  Hard limits are
    enforced by the Pydantic model validation.
    """
    settings = get_settings()
    safety_config = _load_yaml(settings.SAFETY_CONFIG_PATH)

    updated: dict[str, Any] = {}
    if req.max_blast_radius is not None:
        safety_config["max_blast_radius"] = req.max_blast_radius
        updated["max_blast_radius"] = req.max_blast_radius
    if req.max_scale_per_minute is not None:
        safety_config["max_scale_per_minute"] = req.max_scale_per_minute
        updated["max_scale_per_minute"] = req.max_scale_per_minute
    if req.cooldown_seconds is not None:
        safety_config["cooldown_seconds"] = req.cooldown_seconds
        updated["cooldown_seconds"] = req.cooldown_seconds

    _save_yaml(settings.SAFETY_CONFIG_PATH, safety_config)

    log.info("safety_constraints_updated", updates=updated)
    return {"status": "updated", "safety": safety_config}


# ── Helpers ─────────────────────────────────────────────────────────────


def _save_yaml(path: str, data: dict[str, Any]) -> None:
    """Write a dict to a YAML file and update the cache."""
    p = Path(path)
    try:
        p.parent.mkdir(parents=True, exist_ok=True)
        with p.open("w", encoding="utf-8") as fh:
            yaml.safe_dump(data, fh, default_flow_style=False, sort_keys=False)
        _yaml_cache[path] = data
        log.info("yaml_saved", path=path)
    except Exception as exc:
        log.error("yaml_save_error", path=path, error=str(exc))
