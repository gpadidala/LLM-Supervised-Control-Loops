"""Safety manager for the SCL-Governor control loop.

Enforces hard safety constraints, manages action cooldowns, and generates
safe candidate actions based on the current system state and regime.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any
import uuid

from models.action import ActionCandidate, ActionType
from models.state import SystemState
from utils.logger import get_logger

log = get_logger(__name__)


class SafetyManager:
    """Enforces safety constraints and generates safe action candidates.

    Every candidate action must pass validation before it can be executed.
    The safety manager also tracks cooldowns and in-flight actions to prevent
    conflicting or rapid-fire mutations.
    """

    def __init__(self, settings: Any) -> None:
        self.settings = settings
        self.action_cooldowns: dict[str, datetime] = {}   # target -> last_action_time
        self.inflight_actions: list[str] = []              # list of action IDs in progress

    # ------------------------------------------------------------------
    # Candidate generation
    # ------------------------------------------------------------------

    def generate_safe_actions(
        self,
        state: SystemState,
        regime: str,
    ) -> list[ActionCandidate]:
        """Generate candidate actions appropriate for the current state and regime.

        Always includes a NOOP.  Other actions are proposed based on the observed
        metrics and filtered by regime (restricting blast radius in critical mode)
        and cooldown constraints.
        """
        candidates: list[ActionCandidate] = []

        # Always include NOOP
        candidates.append(
            ActionCandidate(
                id=f"noop-{uuid.uuid4().hex[:8]}",
                type=ActionType.NOOP,
                description="Take no action and continue observing.",
                blast_radius=0.0,
                reversibility=1.0,
            )
        )

        # Extract key metrics
        metrics = self._extract_metrics(state)

        # --- Latency high -> scale up, rate limit ---
        p99 = metrics.get("latency_p99", 0.0)
        if p99 > 300:
            candidates.append(
                ActionCandidate(
                    id=f"hscale-{uuid.uuid4().hex[:8]}",
                    type=ActionType.HORIZONTAL_SCALE,
                    description=f"Add replicas to reduce p99 latency (currently {p99:.0f}ms).",
                    target_service="primary-api",
                    parameters={"add_replicas": 2, "current_replicas": 3},
                    blast_radius=0.1,
                    reversibility=1.0,
                    estimated_cost_delta=5.0,
                    estimated_duration_seconds=120,
                    rollback_steps=["Scale replicas back to original count"],
                )
            )
        if p99 > 400:
            candidates.append(
                ActionCandidate(
                    id=f"rlimit-{uuid.uuid4().hex[:8]}",
                    type=ActionType.RATE_LIMIT,
                    description=f"Apply rate limiting to shed excess traffic (p99={p99:.0f}ms).",
                    target_service="primary-api",
                    parameters={"limit_rps": 500},
                    blast_radius=0.15,
                    reversibility=0.9,
                    estimated_cost_delta=0.0,
                    estimated_duration_seconds=30,
                    rollback_steps=["Remove rate limit configuration"],
                )
            )

        # --- Resource utilisation high -> scale up, vertical scale ---
        cpu = metrics.get("cpu_usage", 0.0)
        mem = metrics.get("memory_usage", 0.0)
        if cpu > 80 or mem > 80:
            candidates.append(
                ActionCandidate(
                    id=f"vscale-{uuid.uuid4().hex[:8]}",
                    type=ActionType.VERTICAL_SCALE,
                    description=(
                        f"Increase resource limits (CPU={cpu:.0f}%, MEM={mem:.0f}%)."
                    ),
                    target_service="primary-api",
                    parameters={"cpu_increase_pct": 50, "memory_increase_pct": 50},
                    blast_radius=0.05,
                    reversibility=0.8,
                    estimated_cost_delta=8.0,
                    estimated_duration_seconds=180,
                    rollback_steps=["Revert resource limits to previous values"],
                )
            )

        # --- Error rate high -> circuit break, traffic shift ---
        error_5xx = metrics.get("error_rate_5xx", 0.0)
        if error_5xx > 2.0:
            candidates.append(
                ActionCandidate(
                    id=f"cbreak-{uuid.uuid4().hex[:8]}",
                    type=ActionType.CIRCUIT_BREAK,
                    description=f"Open circuit breaker (5xx rate={error_5xx:.1f}%).",
                    target_service="primary-api",
                    parameters={"target_service": "primary-api"},
                    blast_radius=0.10,
                    reversibility=1.0,
                    estimated_cost_delta=0.0,
                    estimated_duration_seconds=30,
                    rollback_steps=["Close circuit breaker"],
                )
            )
        if error_5xx > 3.0:
            candidates.append(
                ActionCandidate(
                    id=f"tshift-{uuid.uuid4().hex[:8]}",
                    type=ActionType.TRAFFIC_SHIFT,
                    description=f"Shift 20% traffic away (5xx rate={error_5xx:.1f}%).",
                    target_service="primary-api",
                    parameters={"shift_percentage": 20},
                    blast_radius=0.20,
                    reversibility=0.9,
                    estimated_cost_delta=2.0,
                    estimated_duration_seconds=60,
                    rollback_steps=["Revert traffic weights to original values"],
                )
            )

        # --- Cost high -> scale down, spot rebalance ---
        cost_rate = metrics.get("cloud_spend_rate_hr", 0.0)
        if cost_rate > 100 and cpu < 40 and mem < 40:
            candidates.append(
                ActionCandidate(
                    id=f"sdown-{uuid.uuid4().hex[:8]}",
                    type=ActionType.HORIZONTAL_SCALE,
                    description=f"Scale down under-utilised deployment (cost=${cost_rate:.0f}/hr).",
                    target_service="primary-api",
                    parameters={"add_replicas": -1, "current_replicas": 5},
                    blast_radius=0.05,
                    reversibility=1.0,
                    estimated_cost_delta=-5.0,
                    estimated_duration_seconds=120,
                    rollback_steps=["Scale replicas back up"],
                )
            )
            candidates.append(
                ActionCandidate(
                    id=f"spot-{uuid.uuid4().hex[:8]}",
                    type=ActionType.SPOT_REBALANCE,
                    description=f"Rebalance to spot instances (cost=${cost_rate:.0f}/hr).",
                    target_service="primary-api",
                    parameters={"target_spot_percentage": 60},
                    blast_radius=0.10,
                    reversibility=0.7,
                    estimated_cost_delta=-15.0,
                    estimated_duration_seconds=300,
                    rollback_steps=["Migrate workloads back to on-demand instances"],
                )
            )

        # --- Filter by regime (restrict blast radius in critical) ---
        max_blast = self.settings.MAX_BLAST_RADIUS
        if regime == "critical":
            # In critical mode, only allow very low blast-radius actions
            max_blast = min(max_blast, 0.10)
        elif regime == "degraded":
            max_blast = min(max_blast, 0.20)

        candidates = [c for c in candidates if c.blast_radius <= max_blast]

        # --- Filter by cooldown ---
        candidates = [c for c in candidates if self._cooldown_ok(c)]

        # --- Filter out conflicting inflight actions ---
        candidates = [c for c in candidates if not self._has_conflict(c)]

        log.info(
            "safe_actions_generated",
            regime=regime,
            count=len(candidates),
        )
        return candidates

    # ------------------------------------------------------------------
    # Validation
    # ------------------------------------------------------------------

    def validate_action(
        self, action: ActionCandidate
    ) -> tuple[bool, list[str]]:
        """Validate an action against hard safety constraints.

        Returns ``(is_valid, list_of_issues)``.
        """
        issues: list[str] = []

        # Blast radius check
        if action.blast_radius > self.settings.MAX_BLAST_RADIUS:
            issues.append(
                f"Blast radius {action.blast_radius:.2f} exceeds maximum "
                f"{self.settings.MAX_BLAST_RADIUS:.2f}"
            )

        # Minimum replicas check (for scale-down)
        if action.type == ActionType.HORIZONTAL_SCALE:
            add = action.parameters.get("add_replicas", 0)
            current = action.parameters.get("current_replicas", 1)
            if current + add < 1:
                issues.append(
                    f"Cannot scale below 1 replica (current={current}, add={add})"
                )

        # Cooldown check
        if not self._cooldown_ok(action):
            target = action.target_service or "unknown"
            issues.append(
                f"Cooldown active for target '{target}'. "
                f"Last action too recent."
            )

        # Inflight conflict check
        if self._has_conflict(action):
            issues.append(
                f"Conflicting action already in-flight for "
                f"'{action.target_service or 'unknown'}'"
            )

        is_valid = len(issues) == 0
        if not is_valid:
            log.warning(
                "action_validation_failed",
                action_id=action.id,
                issues=issues,
            )
        return is_valid, issues

    # ------------------------------------------------------------------
    # Action tracking
    # ------------------------------------------------------------------

    def record_action(self, action: ActionCandidate) -> None:
        """Record that an action was executed for cooldown tracking."""
        target = action.target_service or action.id
        self.action_cooldowns[target] = datetime.now(timezone.utc)
        self.inflight_actions.append(action.id)
        log.info(
            "action_recorded",
            action_id=action.id,
            target=target,
        )

    def clear_action(self, action_id: str) -> None:
        """Mark an action as completed, remove from in-flight list."""
        if action_id in self.inflight_actions:
            self.inflight_actions.remove(action_id)
            log.info("action_cleared", action_id=action_id)

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _extract_metrics(self, state: SystemState) -> dict[str, float]:
        """Flatten state telemetry into a name->value dict."""
        out: dict[str, float] = {}
        for vec in (
            state.infrastructure,
            state.application,
            state.business,
            state.network,
            state.cost,
        ):
            for m in vec.metrics:
                out[m.name] = m.value
        return out

    def _cooldown_ok(self, action: ActionCandidate) -> bool:
        """Return True if the cooldown for this action's target has elapsed."""
        if action.type == ActionType.NOOP:
            return True
        target = action.target_service or action.id
        last = self.action_cooldowns.get(target)
        if last is None:
            return True
        elapsed = (datetime.now(timezone.utc) - last).total_seconds()
        return elapsed >= self.settings.COOLDOWN_SECONDS

    def _has_conflict(self, action: ActionCandidate) -> bool:
        """Return True if a conflicting action is currently in-flight."""
        if action.type == ActionType.NOOP:
            return False
        # Simple conflict: same target service already has an inflight action
        target = action.target_service or ""
        if not target:
            return False
        for aid in self.inflight_actions:
            # If the action id prefix matches the target, it's a conflict
            # (in production this would be a more sophisticated check)
            if target in aid:
                return True
        return False
