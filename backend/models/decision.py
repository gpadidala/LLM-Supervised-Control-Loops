"""Pydantic models for the SCL-Governor decision, execution, and learning phases.

These models capture the LLM's reasoning, the execution record, the learning
feedback, and the composite output of a full control cycle.
"""

from __future__ import annotations

from datetime import datetime
from enum import Enum
from typing import Any

from pydantic import BaseModel

from models.action import ActionCandidate
from models.state import StateSummary


class AutonomyLevel(str, Enum):
    """How much human oversight the governor requires for this decision."""

    EXECUTE_AUTONOMOUS = "execute_autonomous"
    EXECUTE_WITH_NOTIFICATION = "execute_with_notification"
    RECOMMEND = "recommend"
    ESCALATE = "escalate"


class ExecutionStage(str, Enum):
    """Lifecycle stage of an action being executed."""

    PENDING = "pending"
    PREFLIGHT = "preflight"
    CANARY = "canary"
    PARTIAL = "partial"
    FULL = "full"
    COMPLETED = "completed"
    ROLLED_BACK = "rolled_back"
    FAILED = "failed"


class Decision(BaseModel):
    """The governor's chosen action for one control cycle."""

    cycle_id: str
    timestamp: datetime
    selected_action: ActionCandidate
    reasoning: str
    confidence: float
    autonomy_level: AutonomyLevel
    alternative_actions: list[dict[str, Any]] = []
    rollback_plan: str
    rollback_trigger: str
    simulation_summary: dict[str, Any] = {}
    human_notification: str = ""


class ExecutionRecord(BaseModel):
    """Audit trail for an action that has been or is being executed."""

    decision_id: str
    cycle_id: str
    timestamp: datetime
    action: ActionCandidate
    stage: ExecutionStage = ExecutionStage.PENDING
    pre_state_snapshot: dict[str, Any] = {}
    expected_post_state: dict[str, Any] = {}
    actual_post_state: dict[str, Any] | None = None
    deviation_score: float | None = None
    rolled_back: bool = False
    rollback_reason: str | None = None
    execution_log: list[str] = []


class LearningUpdate(BaseModel):
    """Feedback signals from the Learn phase used to update internal models."""

    cycle_id: str
    timestamp: datetime
    previous_action_accuracy: float | None = None
    prediction_errors: dict[str, float] = {}
    simulation_fidelity: float | None = None
    model_drift_detected: bool = False
    policy_update_pending: bool = False
    reward_signal: float | None = None
    human_overrides: int = 0


class ControlCycleOutput(BaseModel):
    """Complete output of one SCL control cycle -- matches the JSON output spec."""

    cycle_id: str
    timestamp: datetime
    system_regime: str
    state_summary: StateSummary
    prediction: dict[str, Any]
    simulation_results: dict[str, Any]
    decision: dict[str, Any]
    execution_status: str
    learning_update: dict[str, Any]
