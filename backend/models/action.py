"""Pydantic models for SCL-Governor actions.

An action is any mutation the governor can apply to the managed system --
scaling, traffic shifting, circuit breaking, etc.
"""

from __future__ import annotations

from enum import Enum
from typing import Any

from pydantic import BaseModel, Field


class ActionType(str, Enum):
    """Enumeration of supported action categories."""

    HORIZONTAL_SCALE = "horizontal_scale"
    VERTICAL_SCALE = "vertical_scale"
    SPOT_REBALANCE = "spot_rebalance"
    RATE_LIMIT = "rate_limit"
    CIRCUIT_BREAK = "circuit_break"
    TRAFFIC_SHIFT = "traffic_shift"
    RESOURCE_REALLOC = "resource_realloc"
    CONFIG_CHANGE = "config_change"
    COMPOSITE = "composite"
    NOOP = "noop"


class ActionCandidate(BaseModel):
    """A candidate action that the governor may choose to execute."""

    id: str
    type: ActionType
    description: str
    parameters: dict[str, Any] = {}
    target_service: str | None = None
    target_resource: str | None = None
    blast_radius: float = Field(
        default=0.0,
        ge=0.0,
        le=1.0,
        description="Fraction of traffic affected (0.0-1.0)",
    )
    reversibility: float = Field(
        default=1.0,
        ge=0.0,
        le=1.0,
        description="How easily this action can be rolled back (0.0-1.0)",
    )
    estimated_cost_delta: float = 0.0  # $/hr change
    estimated_duration_seconds: int = 60
    sub_actions: list["ActionCandidate"] = []  # for composite actions
    prerequisites: list[str] = []
    rollback_steps: list[str] = []
