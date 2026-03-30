"""Phase 5 -- ACTUATE: Action Dispatch & Execution.

Executes selected actions through infrastructure APIs (Kubernetes, gateways)
with pre-flight safety checks, staged rollout support, and notification
dispatch based on the autonomy level of the decision.
"""

from __future__ import annotations

import asyncio
import time
import uuid
from datetime import datetime
from typing import Any

from models.action import ActionCandidate, ActionType
from models.decision import AutonomyLevel, Decision, ExecutionRecord, ExecutionStage
from models.state import SystemState
from utils.logger import get_logger

logger = get_logger(__name__)

# Staged rollout percentages
_STAGES = [
    ("canary", 0.10),
    ("partial", 0.50),
    ("full", 1.00),
]

# Simulated stage wait time in seconds (real system would check metrics)
_STAGE_WAIT_SECONDS = 2.0

# Cooldown tracking: action_type -> last_execution_timestamp
_cooldown_tracker: dict[str, float] = {}


class ActuatePhase:
    """Executes selected actions through infrastructure APIs with staged rollout."""

    def __init__(
        self,
        k8s_connector: Any = None,
        notification_connector: Any = None,
    ):
        """Initialise the actuate phase.

        Parameters
        ----------
        k8s_connector:
            Object with methods like ``scale_deployment()``, ``patch_hpa()``,
            ``apply_network_policy()``.  Can be ``None`` for demo mode.
        notification_connector:
            Object with ``async send_slack(msg)`` and ``async send_pagerduty(msg, severity)``
            methods.  Can be ``None`` for demo mode.
        """
        self._k8s = k8s_connector
        self._notifier = notification_connector

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    async def execute(
        self,
        decision: Decision,
        state: SystemState,
        cycle_id: str,
    ) -> ExecutionRecord:
        """Execute the decision with pre-flight checks and staged rollout."""
        logger.info(
            "actuate.start",
            cycle_id=cycle_id,
            action_id=decision.selected_action.id,
            action_type=decision.selected_action.type.value,
            autonomy=decision.autonomy_level.value,
        )
        start = time.monotonic()
        decision_id = f"exec-{uuid.uuid4().hex[:12]}"

        action = decision.selected_action
        pre_state = self._state_to_dict(state)

        # 1. Pre-flight checks
        preflight_ok, issues = await self._preflight_checks(action, state)

        record = ExecutionRecord(
            decision_id=decision_id,
            cycle_id=cycle_id,
            timestamp=datetime.utcnow(),
            action=action,
            stage=ExecutionStage.PREFLIGHT,
            pre_state_snapshot=pre_state,
            expected_post_state=self._estimate_post_state(pre_state, action),
            execution_log=[f"[{self._ts()}] Pre-flight check: {'PASSED' if preflight_ok else 'FAILED'}"],
        )

        if not preflight_ok:
            record.stage = ExecutionStage.FAILED
            record.rolled_back = False
            record.rollback_reason = "; ".join(issues)
            record.execution_log.append(f"[{self._ts()}] Aborting: {'; '.join(issues)}")
            await self._notify(decision, record.execution_log)
            logger.warning("actuate.preflight_failed", cycle_id=cycle_id, issues=issues)
            return record

        # 2. Check autonomy level -- only execute if autonomous or with-notification
        if decision.autonomy_level in (AutonomyLevel.RECOMMEND, AutonomyLevel.ESCALATE):
            record.execution_log.append(
                f"[{self._ts()}] Autonomy level is {decision.autonomy_level.value}; "
                f"action recommended but not auto-executed."
            )
            record.stage = ExecutionStage.PENDING
            await self._notify(decision, record.execution_log)
            logger.info("actuate.recommend_only", cycle_id=cycle_id)
            return record

        # 3. Determine if staged rollout is appropriate
        staged = action.type not in (ActionType.NOOP, ActionType.CIRCUIT_BREAK)

        # 4. Execute
        record.stage = ExecutionStage.CANARY if staged else ExecutionStage.FULL
        record.execution_log.append(f"[{self._ts()}] Executing action: {action.type.value}")

        try:
            exec_log = await self._execute_action(action, staged=staged)
            record.execution_log.extend(exec_log)
            record.stage = ExecutionStage.COMPLETED
            record.execution_log.append(f"[{self._ts()}] Execution completed successfully.")

            # Update cooldown tracker
            _cooldown_tracker[action.type.value] = time.monotonic()

        except Exception as exc:
            record.stage = ExecutionStage.FAILED
            record.execution_log.append(f"[{self._ts()}] Execution failed: {exc}")
            record.rolled_back = False
            logger.error("actuate.execution_error", cycle_id=cycle_id, error=str(exc))

        # 5. Send notifications
        await self._notify(decision, record.execution_log)

        elapsed = time.monotonic() - start
        logger.info(
            "actuate.complete",
            cycle_id=cycle_id,
            stage=record.stage.value,
            elapsed_ms=round(elapsed * 1000, 1),
        )
        return record

    # ------------------------------------------------------------------
    # Pre-flight checks
    # ------------------------------------------------------------------

    async def _preflight_checks(
        self,
        action: ActionCandidate,
        state: SystemState,
    ) -> tuple[bool, list[str]]:
        """Validate the action is safe to execute. Returns (passed, issues)."""
        issues: list[str] = []

        # NOOP always passes
        if action.type == ActionType.NOOP:
            return True, []

        # 1. Parameter validation
        if action.type == ActionType.HORIZONTAL_SCALE:
            add = action.parameters.get("add_replicas", 0)
            if add < 1 or add > 20:
                issues.append(f"add_replicas={add} outside safe range [1, 20]")

        if action.type == ActionType.RATE_LIMIT:
            limit = action.parameters.get("limit_rps", 0)
            if limit < 10:
                issues.append(f"Rate limit {limit} req/s is too aggressive")

        # 2. Cooldown period check
        last_exec = _cooldown_tracker.get(action.type.value, 0)
        elapsed_since_last = time.monotonic() - last_exec
        cooldown = action.estimated_duration_seconds
        if elapsed_since_last < cooldown and last_exec > 0:
            issues.append(
                f"Cooldown not elapsed: {elapsed_since_last:.0f}s < {cooldown}s since last {action.type.value}"
            )

        # 3. Blast radius check
        if action.blast_radius > 0.5:
            issues.append(f"Blast radius {action.blast_radius:.0%} exceeds 50% safety limit")

        # 4. Resource budget check (simple heuristic)
        if action.estimated_cost_delta > 50:
            issues.append(f"Estimated cost increase ${action.estimated_cost_delta:.2f}/hr exceeds budget guard")

        # 5. Cluster health check
        state_dict = self._state_to_dict(state)
        node_health = state_dict.get("node_health", 1.0)
        if node_health < 0.5:
            issues.append(f"Cluster node health too low ({node_health:.0%}) for safe action execution")

        return len(issues) == 0, issues

    # ------------------------------------------------------------------
    # Action execution
    # ------------------------------------------------------------------

    async def _execute_action(self, action: ActionCandidate, staged: bool = True) -> list[str]:
        """Execute the action, optionally with staged rollout."""
        log: list[str] = []

        if action.type == ActionType.NOOP:
            log.append(f"[{self._ts()}] NOOP: no changes applied.")
            return log

        if staged:
            log.extend(await self._staged_rollout(action))
        else:
            log.extend(await self._immediate_execute(action))

        return log

    async def _staged_rollout(self, action: ActionCandidate) -> list[str]:
        """Apply action in stages: canary (10%) -> partial (50%) -> full (100%)."""
        log: list[str] = []

        for stage_name, pct in _STAGES:
            log.append(f"[{self._ts()}] Stage '{stage_name}': applying to {pct:.0%} of target.")

            # Execute at this stage
            stage_log = await self._dispatch_to_infrastructure(action, percentage=pct)
            log.extend(stage_log)

            # Wait and check (simulated health check between stages)
            if pct < 1.0:
                log.append(f"[{self._ts()}] Waiting {_STAGE_WAIT_SECONDS}s for metrics stabilisation...")
                await asyncio.sleep(_STAGE_WAIT_SECONDS)

                # Simulated health check
                healthy = self._simulated_health_check(action, stage_name)
                if not healthy:
                    log.append(f"[{self._ts()}] Health check FAILED at stage '{stage_name}'. Halting rollout.")
                    break
                log.append(f"[{self._ts()}] Health check PASSED at stage '{stage_name}'.")

        return log

    async def _immediate_execute(self, action: ActionCandidate) -> list[str]:
        """Execute action immediately without staging."""
        log: list[str] = []
        log.append(f"[{self._ts()}] Immediate execution (no staging).")
        stage_log = await self._dispatch_to_infrastructure(action, percentage=1.0)
        log.extend(stage_log)
        return log

    async def _dispatch_to_infrastructure(
        self,
        action: ActionCandidate,
        percentage: float,
    ) -> list[str]:
        """Dispatch to the actual infrastructure connector or simulate."""
        log: list[str] = []
        target = action.target_service or action.target_resource or "default"

        if self._k8s is not None:
            # Real Kubernetes execution
            try:
                if action.type == ActionType.HORIZONTAL_SCALE:
                    add = action.parameters.get("add_replicas", 1)
                    scaled_add = max(1, int(add * percentage))
                    await self._k8s.scale_deployment(
                        deployment=target,
                        replicas_delta=scaled_add,
                    )
                    log.append(f"[{self._ts()}] K8s: scaled {target} by +{scaled_add} replicas.")

                elif action.type == ActionType.VERTICAL_SCALE:
                    cpu_inc = action.parameters.get("cpu_increase_pct", 50)
                    mem_inc = action.parameters.get("memory_increase_pct", 50)
                    await self._k8s.patch_hpa(
                        deployment=target,
                        cpu_request_increase_pct=int(cpu_inc * percentage),
                        memory_request_increase_pct=int(mem_inc * percentage),
                    )
                    log.append(f"[{self._ts()}] K8s: patched resource limits for {target}.")

                elif action.type == ActionType.RATE_LIMIT:
                    limit = action.parameters.get("limit_rps", 500)
                    effective_limit = int(limit / percentage) if percentage > 0 else limit
                    log.append(f"[{self._ts()}] Gateway: rate limit set to {effective_limit} req/s for {target}.")

                elif action.type == ActionType.CIRCUIT_BREAK:
                    log.append(f"[{self._ts()}] Mesh: circuit breaker OPEN for {target}.")

                elif action.type == ActionType.TRAFFIC_SHIFT:
                    shift_pct = action.parameters.get("shift_percentage", 20) * percentage
                    log.append(f"[{self._ts()}] Mesh: shifted {shift_pct:.0f}% traffic away from {target}.")

                else:
                    log.append(f"[{self._ts()}] K8s: executed {action.type.value} on {target} at {percentage:.0%}.")

            except Exception as exc:
                log.append(f"[{self._ts()}] K8s ERROR: {exc}")
                raise
        else:
            # Demo / simulation mode
            log.append(
                f"[{self._ts()}] [DEMO] Would execute {action.type.value} on '{target}' "
                f"at {percentage:.0%} rollout."
            )
            self._log_demo_details(action, percentage, log)

        return log

    def _log_demo_details(self, action: ActionCandidate, percentage: float, log: list[str]) -> None:
        """Add detailed demo-mode log entries showing what would happen."""
        target = action.target_service or "service"

        if action.type == ActionType.HORIZONTAL_SCALE:
            add = action.parameters.get("add_replicas", 1)
            current = action.parameters.get("current_replicas", 3)
            scaled_add = max(1, int(add * percentage))
            log.append(
                f"[{self._ts()}] [DEMO] Scale {target}: {current} -> {current + scaled_add} replicas"
            )

        elif action.type == ActionType.RATE_LIMIT:
            limit = action.parameters.get("limit_rps", 500)
            log.append(f"[{self._ts()}] [DEMO] Rate limit {target} to {limit} req/s")

        elif action.type == ActionType.CIRCUIT_BREAK:
            log.append(f"[{self._ts()}] [DEMO] Open circuit breaker for {target}")

        elif action.type == ActionType.TRAFFIC_SHIFT:
            shift = action.parameters.get("shift_percentage", 20) * percentage
            log.append(f"[{self._ts()}] [DEMO] Shift {shift:.0f}% traffic away from {target}")

        elif action.type == ActionType.VERTICAL_SCALE:
            cpu_inc = action.parameters.get("cpu_increase_pct", 50)
            mem_inc = action.parameters.get("memory_increase_pct", 50)
            log.append(
                f"[{self._ts()}] [DEMO] Increase resources: CPU +{cpu_inc}%, Memory +{mem_inc}%"
            )

    @staticmethod
    def _simulated_health_check(action: ActionCandidate, stage: str) -> bool:
        """Simulated health check between rollout stages.

        In production this would query live metrics and compare against
        the expected post-state from the simulation.  For demo mode we
        return True with high probability.
        """
        import random
        # 95% chance of passing in demo mode
        return random.random() < 0.95

    # ------------------------------------------------------------------
    # Notifications
    # ------------------------------------------------------------------

    async def _notify(self, decision: Decision, execution_log: list[str]) -> None:
        """Send notifications based on autonomy level."""
        autonomy = decision.autonomy_level
        message = decision.human_notification or self._format_notification(decision, execution_log)

        if autonomy == AutonomyLevel.EXECUTE_AUTONOMOUS:
            # Just log, no external notification
            logger.info("actuate.notify.log_only", action=decision.selected_action.id)

        elif autonomy == AutonomyLevel.EXECUTE_WITH_NOTIFICATION:
            await self._send_slack(message)

        elif autonomy == AutonomyLevel.RECOMMEND:
            await self._send_slack(message)
            await self._send_pagerduty(message, severity="low")

        elif autonomy == AutonomyLevel.ESCALATE:
            await self._send_slack(f"[URGENT] {message}")
            await self._send_pagerduty(message, severity="high")

    async def _send_slack(self, message: str) -> None:
        """Send a Slack notification."""
        if self._notifier is not None:
            try:
                await self._notifier.send_slack(message)
                logger.info("actuate.slack_sent")
            except Exception as exc:
                logger.warning("actuate.slack_failed", error=str(exc))
        else:
            logger.info("actuate.slack_demo", message=message[:200])

    async def _send_pagerduty(self, message: str, severity: str = "low") -> None:
        """Send a PagerDuty notification."""
        if self._notifier is not None:
            try:
                await self._notifier.send_pagerduty(message, severity)
                logger.info("actuate.pagerduty_sent", severity=severity)
            except Exception as exc:
                logger.warning("actuate.pagerduty_failed", error=str(exc))
        else:
            logger.info("actuate.pagerduty_demo", severity=severity, message=message[:200])

    @staticmethod
    def _format_notification(decision: Decision, execution_log: list[str]) -> str:
        """Format a notification message from decision + execution log."""
        action = decision.selected_action
        log_excerpt = "\n".join(execution_log[-5:])
        return (
            f"SCL-Governor Action Report\n"
            f"==========================\n"
            f"Action: {action.type.value}\n"
            f"Target: {action.target_service or 'system'}\n"
            f"Autonomy: {decision.autonomy_level.value}\n"
            f"Confidence: {decision.confidence:.0%}\n"
            f"Reasoning: {decision.reasoning}\n"
            f"\nExecution Log (last 5):\n{log_excerpt}\n"
            f"\nRollback Plan: {decision.rollback_plan}\n"
            f"Rollback Trigger: {decision.rollback_trigger}"
        )

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def _estimate_post_state(
        self,
        pre_state: dict[str, float],
        action: ActionCandidate,
    ) -> dict[str, float]:
        """Estimate the post-action state (simple heuristic for audit trail)."""
        post = dict(pre_state)

        if action.type == ActionType.HORIZONTAL_SCALE:
            current = action.parameters.get("current_replicas", 3)
            add = action.parameters.get("add_replicas", 1)
            factor = current / (current + add)
            post["cpu_usage"] = pre_state.get("cpu_usage", 50) * factor
            post["latency_p99"] = pre_state.get("latency_p99", 200) * (0.7 + 0.3 * factor)

        elif action.type == ActionType.RATE_LIMIT:
            limit = action.parameters.get("limit_rps", 500)
            current_rps = pre_state.get("request_rate", 800)
            if current_rps > limit:
                post["request_rate"] = float(limit)
                post["latency_p99"] = pre_state.get("latency_p99", 200) * 0.7

        elif action.type == ActionType.CIRCUIT_BREAK:
            post["error_rate_5xx"] = pre_state.get("error_rate_5xx", 2) * 0.3

        return {k: round(v, 2) for k, v in post.items()}

    @staticmethod
    def _state_to_dict(state: SystemState) -> dict[str, float]:
        out: dict[str, float] = {}
        for vec in (state.infrastructure, state.application, state.business, state.network, state.cost):
            for m in vec.metrics:
                out[m.name] = m.value
        return out

    @staticmethod
    def _ts() -> str:
        """Return an ISO-format timestamp string."""
        return datetime.utcnow().strftime("%H:%M:%S.%f")[:-3]
