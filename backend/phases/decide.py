"""Phase 4 -- DECIDE: Optimal Control + LLM Policy Selection.

Selects the optimal action from Pareto-optimal candidates using multi-objective
safety filters, LLM reasoning (with rule-based fallback), confidence-gated
autonomy, and automatic rollback plan generation.
"""

from __future__ import annotations

import time
from datetime import datetime
from typing import Any

from config import get_settings
from models.action import ActionCandidate, ActionType
from models.decision import AutonomyLevel, Decision
from models.prediction import PredictionOutput
from models.simulation import SimulationResult, SimulationSuite
from models.state import SystemState
from utils.logger import get_logger

logger = get_logger(__name__)


class DecidePhase:
    """Selects optimal action using multi-objective optimization + LLM reasoning."""

    def __init__(self, llm_provider: Any = None, settings: Any = None):
        self._llm = llm_provider
        self._settings = settings or get_settings()

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    async def execute(
        self,
        state: SystemState,
        prediction: PredictionOutput,
        simulation: SimulationSuite,
        cycle_id: str,
    ) -> Decision:
        """Select the optimal action with full reasoning chain."""
        logger.info("decide.start", cycle_id=cycle_id)
        start = time.monotonic()

        # Build a quick lookup: action_id -> ActionCandidate (from simulation metadata)
        # We reconstruct minimal action info from simulation results
        action_lookup = self._build_action_lookup(simulation)

        # 1. Filter to Pareto-optimal results
        pareto_results = [
            r for r in simulation.results if r.action_id in simulation.pareto_frontier
        ]
        if not pareto_results:
            pareto_results = list(simulation.results)

        # 2. Apply safety filters
        safe_results = self._apply_safety_filters(pareto_results, action_lookup)

        if not safe_results:
            # Everything filtered out -- fall back to NOOP
            logger.warning("decide.all_filtered", cycle_id=cycle_id)
            noop_action = ActionCandidate(
                id="noop-fallback",
                type=ActionType.NOOP,
                description="No safe action available; defaulting to no-op.",
            )
            return Decision(
                cycle_id=cycle_id,
                timestamp=datetime.utcnow(),
                selected_action=noop_action,
                reasoning="All candidate actions were filtered out by safety constraints. "
                          "Defaulting to no-op and escalating for human review.",
                confidence=0.0,
                autonomy_level=AutonomyLevel.ESCALATE,
                rollback_plan="N/A -- no action taken.",
                rollback_trigger="N/A",
                human_notification="All actions failed safety filters. Manual review required.",
            )

        # 3. LLM or rule-based selection
        if self._llm is not None:
            try:
                selected_id, reasoning, confidence = await self._llm_policy_reasoning(
                    state, safe_results, action_lookup,
                )
            except Exception as exc:
                logger.warning("decide.llm_error", error=str(exc))
                selected_id, reasoning, confidence = self._rule_based_selection(safe_results)
        else:
            selected_id, reasoning, confidence = self._rule_based_selection(safe_results)

        # Find the selected simulation result
        selected_sim = next((r for r in safe_results if r.action_id == selected_id), safe_results[0])
        selected_action = action_lookup.get(
            selected_id,
            ActionCandidate(
                id=selected_id,
                type=ActionType.NOOP,
                description="Selected action",
            ),
        )

        # 4. Determine autonomy level
        risk_score = selected_sim.sla_breach_probability
        autonomy = self._determine_autonomy_level(confidence, risk_score, state.regime)

        # 5. Generate rollback plan
        rollback_plan, rollback_trigger = self._generate_rollback_plan(selected_action)

        # 6. Build alternative actions summary
        alternatives = []
        for r in safe_results:
            if r.action_id != selected_id:
                alternatives.append({
                    "action_id": r.action_id,
                    "expected_objective": r.expected_objective,
                    "sla_breach_prob": r.sla_breach_probability,
                    "cvar_95": r.cvar_alpha,
                })

        # 7. Simulation summary for audit
        sim_summary = {
            "total_actions_evaluated": len(simulation.results),
            "pareto_frontier_size": len(simulation.pareto_frontier),
            "safety_filtered_count": len(pareto_results) - len(safe_results),
            "selected_expected_obj": selected_sim.expected_objective,
            "selected_obj_std": selected_sim.stability_score,
            "selected_var_95": selected_sim.var_alpha,
            "selected_cvar_95": selected_sim.cvar_alpha,
            "selected_sla_breach_prob": selected_sim.sla_breach_probability,
        }

        # 8. Human notification message
        notification = self._build_notification(selected_action, autonomy, confidence, risk_score, reasoning)

        elapsed = time.monotonic() - start
        logger.info(
            "decide.complete",
            cycle_id=cycle_id,
            selected=selected_id,
            autonomy=autonomy.value,
            confidence=round(confidence, 3),
            elapsed_ms=round(elapsed * 1000, 1),
        )

        return Decision(
            cycle_id=cycle_id,
            timestamp=datetime.utcnow(),
            selected_action=selected_action,
            reasoning=reasoning,
            confidence=round(confidence, 4),
            autonomy_level=autonomy,
            alternative_actions=alternatives,
            rollback_plan=rollback_plan,
            rollback_trigger=rollback_trigger,
            simulation_summary=sim_summary,
            human_notification=notification,
        )

    # ------------------------------------------------------------------
    # Safety filters
    # ------------------------------------------------------------------

    def _apply_safety_filters(
        self,
        results: list[SimulationResult],
        actions: dict[str, ActionCandidate],
    ) -> list[SimulationResult]:
        """Filter out actions that violate safety constraints."""
        safe: list[SimulationResult] = []

        max_blast = self._settings.MAX_BLAST_RADIUS
        sla_breach_limit = 0.30
        cvar_limit = -0.5  # reject actions with very negative CVaR

        for r in results:
            action = actions.get(r.action_id)
            reasons: list[str] = []

            # SLA breach probability check
            if r.sla_breach_probability > sla_breach_limit:
                reasons.append(f"SLA breach prob {r.sla_breach_probability:.2f} > {sla_breach_limit}")

            # CVaR check (very negative = high tail risk)
            if r.cvar_alpha < cvar_limit:
                reasons.append(f"CVaR {r.cvar_alpha:.2f} < {cvar_limit}")

            # Blast radius check
            if action and action.blast_radius > max_blast:
                # Allow in critical regime
                if True:  # We'd check regime here but keep safe by default
                    reasons.append(f"Blast radius {action.blast_radius:.2f} > {max_blast}")

            # Reversibility check (skip for NOOP)
            if action and action.type != ActionType.NOOP and action.reversibility < 0.3:
                reasons.append(f"Low reversibility {action.reversibility:.2f}")

            if reasons:
                logger.debug(
                    "decide.safety_filter",
                    action_id=r.action_id,
                    reasons=reasons,
                )
            else:
                safe.append(r)

        return safe

    # ------------------------------------------------------------------
    # LLM policy reasoning
    # ------------------------------------------------------------------

    async def _llm_policy_reasoning(
        self,
        state: SystemState,
        candidates: list[SimulationResult],
        actions: dict[str, ActionCandidate],
    ) -> tuple[str, str, float]:
        """Ask LLM to reason over candidates and select best action.

        Returns (selected_action_id, reasoning, confidence).
        """
        prompt = self._build_decision_prompt(state, candidates, actions)
        response = await self._llm.reason(prompt)
        return self._parse_decision_response(response, candidates)

    def _build_decision_prompt(
        self,
        state: SystemState,
        candidates: list[SimulationResult],
        actions: dict[str, ActionCandidate],
    ) -> str:
        """Build a structured prompt for LLM decision-making."""
        # Current state summary
        state_dict = self._state_to_dict(state)
        state_lines = [f"  {k}: {v:.2f}" for k, v in sorted(state_dict.items())]

        # Anomalies
        anom_lines = [
            f"  {a.metric_name} (MAD={a.mad_score:.2f})"
            for a in state.derived.anomaly_scores
            if a.is_anomalous
        ]

        # Candidate actions with simulation results
        cand_lines: list[str] = []
        for r in candidates:
            action = actions.get(r.action_id)
            desc = action.description if action else "Unknown action"
            atype = action.type.value if action else "unknown"
            cand_lines.append(
                f"  [{r.action_id}] type={atype}: {desc}\n"
                f"    E[obj]={r.expected_objective:.4f}, stability={r.stability_score:.4f}, "
                f"VaR={r.var_alpha:.4f}, CVaR={r.cvar_alpha:.4f}, "
                f"P(SLA_breach)={r.sla_breach_probability:.3f}"
            )

        prompt = (
            "You are the decision engine for an autonomous infrastructure governor. "
            "Select the single best action from the candidates below.\n\n"
            f"System regime: {state.regime}\n\n"
            f"Current metrics:\n" + "\n".join(state_lines) + "\n\n"
            f"Anomalies:\n" + ("\n".join(anom_lines) if anom_lines else "  None") + "\n\n"
            f"Candidate actions (all Pareto-optimal and safety-filtered):\n"
            + "\n".join(cand_lines) + "\n\n"
            "Respond in exactly this format:\n"
            "SELECTED: <action_id>\n"
            "CONFIDENCE: <float 0-1>\n"
            "REASONING: <1-3 sentences explaining your choice>\n"
        )
        return prompt

    @staticmethod
    def _parse_decision_response(
        response: str,
        candidates: list[SimulationResult],
    ) -> tuple[str, str, float]:
        """Parse the structured LLM response."""
        selected_id = candidates[0].action_id
        reasoning = "LLM decision"
        confidence = 0.5

        for line in response.strip().split("\n"):
            line = line.strip()
            if line.upper().startswith("SELECTED:"):
                raw_id = line.split(":", 1)[1].strip()
                # Validate the ID against actual candidates
                valid_ids = {c.action_id for c in candidates}
                if raw_id in valid_ids:
                    selected_id = raw_id
            elif line.upper().startswith("CONFIDENCE:"):
                try:
                    val = float(line.split(":", 1)[1].strip())
                    confidence = max(0.0, min(1.0, val))
                except ValueError:
                    pass
            elif line.upper().startswith("REASONING:"):
                reasoning = line.split(":", 1)[1].strip()

        return selected_id, reasoning, confidence

    # ------------------------------------------------------------------
    # Rule-based selection (fallback)
    # ------------------------------------------------------------------

    @staticmethod
    def _rule_based_selection(
        candidates: list[SimulationResult],
    ) -> tuple[str, str, float]:
        """Fallback: select action with best expected objective from Pareto set."""
        if not candidates:
            return "noop-fallback", "No candidates available.", 0.0

        # Sort by expected objective descending
        ranked = sorted(candidates, key=lambda r: r.expected_objective, reverse=True)
        best = ranked[0]

        # Build reasoning from simulation metrics
        reasoning_parts: list[str] = [
            f"Selected {best.action_id} based on highest expected objective "
            f"({best.expected_objective:.4f}).",
        ]
        if best.sla_breach_probability < 0.05:
            reasoning_parts.append("SLA breach risk is low.")
        elif best.sla_breach_probability < 0.15:
            reasoning_parts.append("SLA breach risk is moderate but acceptable.")

        if len(ranked) > 1:
            runner_up = ranked[1]
            reasoning_parts.append(
                f"Runner-up was {runner_up.action_id} "
                f"(E[obj]={runner_up.expected_objective:.4f})."
            )

        reasoning = " ".join(reasoning_parts)

        # Confidence: normalised expected objective relative to range
        if len(ranked) > 1:
            obj_range = ranked[0].expected_objective - ranked[-1].expected_objective
            if obj_range > 0:
                confidence = 0.5 + 0.5 * (best.expected_objective - ranked[-1].expected_objective) / obj_range
            else:
                confidence = 0.6
        else:
            confidence = 0.7 if best.expected_objective > 0 else 0.4

        confidence = max(0.1, min(0.95, confidence))
        return best.action_id, reasoning, round(confidence, 3)

    # ------------------------------------------------------------------
    # Autonomy level
    # ------------------------------------------------------------------

    def _determine_autonomy_level(
        self,
        confidence: float,
        risk: float,
        regime: str,
    ) -> AutonomyLevel:
        """Confidence-gated autonomy determination.

        Higher confidence + lower risk = more autonomous.
        Critical regime forces at least notification.
        """
        high = self._settings.CONFIDENCE_THRESHOLD_HIGH
        medium = self._settings.CONFIDENCE_THRESHOLD_MEDIUM
        low = self._settings.CONFIDENCE_THRESHOLD_LOW

        if regime == "critical":
            # In critical regime, never fully autonomous
            if confidence >= high and risk < 0.1:
                return AutonomyLevel.EXECUTE_WITH_NOTIFICATION
            elif confidence >= medium:
                return AutonomyLevel.RECOMMEND
            return AutonomyLevel.ESCALATE

        if confidence >= high and risk < 0.15:
            return AutonomyLevel.EXECUTE_AUTONOMOUS
        elif confidence >= medium and risk < 0.3:
            return AutonomyLevel.EXECUTE_WITH_NOTIFICATION
        elif confidence >= low:
            return AutonomyLevel.RECOMMEND
        return AutonomyLevel.ESCALATE

    # ------------------------------------------------------------------
    # Rollback planning
    # ------------------------------------------------------------------

    @staticmethod
    def _generate_rollback_plan(action: ActionCandidate) -> tuple[str, str]:
        """Generate a rollback plan and trigger condition for the action."""

        if action.type == ActionType.HORIZONTAL_SCALE:
            add = action.parameters.get("add_replicas", 1)
            plan = (
                f"Scale down by {add} replica(s) to restore previous replica count. "
                f"Drain connections gracefully before terminating pods."
            )
            trigger = (
                "If p99 latency does not improve by >10% within 120 seconds of scaling, "
                "or if error rate increases, revert and escalate."
            )

        elif action.type == ActionType.VERTICAL_SCALE:
            plan = (
                "Revert resource limits to previous values. "
                "This requires a pod restart; perform rolling restart to avoid downtime."
            )
            trigger = (
                "If memory or CPU usage does not decrease within 180 seconds, "
                "or if OOM kills occur, revert immediately."
            )

        elif action.type == ActionType.RATE_LIMIT:
            plan = (
                "Remove the rate limit by updating the ingress/gateway configuration "
                "to restore previous throughput limits."
            )
            trigger = (
                "If legitimate traffic is being rejected (4xx rate > 5%) "
                "after 60 seconds, revert the rate limit."
            )

        elif action.type == ActionType.CIRCUIT_BREAK:
            plan = (
                "Close the circuit breaker to restore traffic to the target service. "
                "Monitor error rates on restored connections."
            )
            trigger = (
                "If downstream service remains unhealthy after 300 seconds, "
                "keep circuit open and escalate for investigation."
            )

        elif action.type == ActionType.TRAFFIC_SHIFT:
            shift = action.parameters.get("shift_percentage", 20)
            plan = (
                f"Revert traffic distribution to original weights, "
                f"shifting {shift}% back to the primary target."
            )
            trigger = (
                "If the secondary target shows degradation (p99 > 500ms or error_rate > 3%) "
                "within 120 seconds, revert traffic shift."
            )

        elif action.type == ActionType.NOOP:
            plan = "N/A -- no action was taken."
            trigger = "N/A"

        else:
            # Generic rollback using the action's own rollback_steps if available
            if action.rollback_steps:
                plan = "Execute rollback steps: " + "; ".join(action.rollback_steps)
            else:
                plan = (
                    f"Revert the {action.type.value} action on {action.target_service or 'target'}. "
                    f"Consult runbook for detailed rollback procedure."
                )
            trigger = (
                "If key metrics (p99, error_rate, CPU) do not improve within 120 seconds "
                "after action execution, trigger rollback."
            )

        return plan, trigger

    # ------------------------------------------------------------------
    # Notification builder
    # ------------------------------------------------------------------

    @staticmethod
    def _build_notification(
        action: ActionCandidate,
        autonomy: AutonomyLevel,
        confidence: float,
        risk: float,
        reasoning: str,
    ) -> str:
        """Build a human-readable notification message."""
        level_label = {
            AutonomyLevel.EXECUTE_AUTONOMOUS: "AUTO-EXECUTED",
            AutonomyLevel.EXECUTE_WITH_NOTIFICATION: "EXECUTED (notifying)",
            AutonomyLevel.RECOMMEND: "RECOMMENDATION",
            AutonomyLevel.ESCALATE: "ESCALATION REQUIRED",
        }
        label = level_label.get(autonomy, "INFO")

        return (
            f"[{label}] SCL-Governor action: {action.type.value}\n"
            f"Target: {action.target_service or 'system'}\n"
            f"Confidence: {confidence:.0%} | Risk: {risk:.0%}\n"
            f"Reasoning: {reasoning}\n"
            f"Description: {action.description}"
        )

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _build_action_lookup(simulation: SimulationSuite) -> dict[str, ActionCandidate]:
        """Reconstruct action lookup from simulation results.

        In a full system the action catalog is passed through; here we
        create minimal ActionCandidate stubs from the simulation data so
        the decide phase can still reference them.
        """
        lookup: dict[str, ActionCandidate] = {}
        for r in simulation.results:
            # If scenario results contain enough info, reconstruct
            lookup[r.action_id] = ActionCandidate(
                id=r.action_id,
                type=ActionType.NOOP,
                description=r.action_description or f"Action {r.action_id}",
            )
        return lookup

    @staticmethod
    def _state_to_dict(state: SystemState) -> dict[str, float]:
        out: dict[str, float] = {}
        for vec in (state.infrastructure, state.application, state.business, state.network, state.cost):
            for m in vec.metrics:
                out[m.name] = m.value
        return out
