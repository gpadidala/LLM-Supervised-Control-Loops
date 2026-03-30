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
    """Return the current SCL configuration in the ConfigData shape the frontend expects."""
    settings = get_settings()
    scl_yaml = _load_yaml(settings.SCL_CONFIG_PATH)
    safety_yaml = _load_yaml(settings.SAFETY_CONFIG_PATH)

    # Extract objective weights from YAML (prefer "normal" regime weights)
    yaml_weights = scl_yaml.get("objective_weights", {})
    normal_weights = yaml_weights.get("normal", yaml_weights)

    # Extract safety hard constraints
    hard = safety_yaml.get("hard_constraints", {})

    governor = get_governor()

    return {
        "cycle_interval_seconds": settings.CONTROL_CYCLE_INTERVAL,
        "objective_weights": {
            "performance": normal_weights.get("performance", 0.30),
            "cost": normal_weights.get("cost", 0.20),
            "risk": normal_weights.get("risk", 0.20),
            "stability": normal_weights.get("stability", 0.15),
            "business": normal_weights.get("business", 0.15),
        },
        "confidence_thresholds": {
            "high": settings.CONFIDENCE_THRESHOLD_HIGH,
            "medium": settings.CONFIDENCE_THRESHOLD_MEDIUM,
            "low": settings.CONFIDENCE_THRESHOLD_LOW,
        },
        "safety_constraints": {
            "min_replicas": hard.get("minimum_replicas", {}).get("default", 2),
            "budget_ceiling": hard.get("budget_ceiling", {}).get("daily_max_usd", 1000),
            "max_blast_radius": settings.MAX_BLAST_RADIUS,
            "max_concurrent_changes": hard.get("rate_of_change", {}).get("max_config_changes_per_hour", 10),
            "cooldown_seconds": settings.COOLDOWN_SECONDS,
        },
        "connectors": {
            "prometheus": await _check_prometheus(settings.PROMETHEUS_URL),
            "kubernetes": governor.k8s is not None,
            "llm": governor.llm.is_available,
            "slack": bool(settings.SLACK_WEBHOOK_URL),
            "pagerduty": bool(settings.PAGERDUTY_API_KEY),
        },
    }


async def _check_prometheus(url: str) -> bool:
    """Quick check if Prometheus is reachable."""
    try:
        import httpx
        async with httpx.AsyncClient(timeout=httpx.Timeout(3.0)) as client:
            resp = await client.get(f"{url}/-/healthy")
            return resp.status_code == 200
    except Exception:
        return False


@router.put("/")
async def update_config(body: dict[str, Any]) -> dict[str, Any]:
    """Update configuration from the frontend ConfigData shape.

    Accepts the same shape returned by ``GET /``.  Maps the nested
    structure back to the underlying YAML files and runtime settings.
    """
    settings = get_settings()
    scl_config = _load_yaml(settings.SCL_CONFIG_PATH)
    safety_config = _load_yaml(settings.SAFETY_CONFIG_PATH)
    updated_keys: list[str] = []

    # Objective weights
    if "objective_weights" in body:
        w = body["objective_weights"]
        normal = scl_config.setdefault("objective_weights", {}).setdefault("normal", {})
        for k in ("performance", "cost", "risk", "stability", "business"):
            if k in w:
                normal[k] = float(w[k])
        updated_keys.append("objective_weights")

    # Confidence thresholds
    if "confidence_thresholds" in body:
        t = body["confidence_thresholds"]
        scl_config.setdefault("confidence_thresholds", {}).update(
            {k: float(v) for k, v in t.items() if k in ("high", "medium", "low")}
        )
        updated_keys.append("confidence_thresholds")

    # Safety constraints
    if "safety_constraints" in body:
        s = body["safety_constraints"]
        hard = safety_config.setdefault("hard_constraints", {})
        if "min_replicas" in s:
            hard.setdefault("minimum_replicas", {})["default"] = int(s["min_replicas"])
        if "budget_ceiling" in s:
            hard.setdefault("budget_ceiling", {})["daily_max_usd"] = float(s["budget_ceiling"])
        if "max_blast_radius" in s:
            hard.setdefault("blast_radius", {})["max_traffic_percent"] = int(float(s["max_blast_radius"]) * 100)
        if "cooldown_seconds" in s:
            hard.setdefault("cooldown", {})["default_seconds"] = int(s["cooldown_seconds"])
        updated_keys.append("safety_constraints")

    # Cycle interval
    if "cycle_interval_seconds" in body:
        scl_config.setdefault("governor", {})["cycle_interval_seconds"] = int(body["cycle_interval_seconds"])
        updated_keys.append("cycle_interval_seconds")

    # Persist
    _save_yaml(settings.SCL_CONFIG_PATH, scl_config)
    _save_yaml(settings.SAFETY_CONFIG_PATH, safety_config)

    log.info("config_updated", keys=updated_keys)
    return {"status": "updated", "keys": updated_keys}


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
