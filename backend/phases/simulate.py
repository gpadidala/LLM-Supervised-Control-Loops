"""Phase 3 -- SIMULATE: Multi-Scenario SDE-Based Simulation.

Runs Monte Carlo simulation of candidate actions using a simplified
stochastic differential equation (SDE) model with Euler--Maruyama
integration.  Produces per-action statistics (expected objective, VaR, CVaR,
SLA breach probability) and identifies the Pareto-optimal frontier.
"""

from __future__ import annotations

import time
from datetime import datetime, timezone
from typing import Any

import numpy as np

from config import get_settings
from models.action import ActionCandidate, ActionType
from models.prediction import PredictionOutput
from models.simulation import ScenarioResult, SimulationResult, SimulationSuite
from models.state import SystemState
from utils.logger import get_logger
from utils.statistics import compute_cvar, compute_pareto_frontier

logger = get_logger(__name__)

# Objective weights
_W_PERF = 0.35
_W_COST = 0.15
_W_RISK = 0.20
_W_STAB = 0.15
_W_BIZ = 0.15

# SDE parameters
_THETA = 0.5       # mean-reversion speed
_DT = 1.0          # time-step in abstract units
_N_STEPS = 20      # evolution steps per scenario

# SLA thresholds used for compliance checking
_SLA_P99_LIMIT_MS = 500.0
_SLA_ERROR_LIMIT_PCT = 5.0


class SimulatePhase:
    """Runs Monte Carlo simulation of candidate actions using simplified SDE model."""

    def __init__(self, settings: Any | None = None):
        self._settings = settings or get_settings()
        self.n_scenarios: int = self._settings.SIMULATION_SCENARIOS
        self._rng = np.random.default_rng(seed=None)  # non-deterministic

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    async def execute(
        self,
        state: SystemState,
        prediction: PredictionOutput,
        actions: list[ActionCandidate],
        cycle_id: str,
    ) -> SimulationSuite:
        """Simulate all candidate actions and compute Pareto frontier."""
        logger.info("simulate.start", cycle_id=cycle_id, n_actions=len(actions))
        start = time.monotonic()

        state_dict = self._state_to_dict(state)
        volatility = self._estimate_volatility(state)

        results: list[SimulationResult] = []
        total_scenarios = 0

        for action in actions:
            sim_result = self._simulate_action(state_dict, action, self.n_scenarios, volatility)
            results.append(sim_result)
            total_scenarios += sim_result.n_scenarios

        # Pareto frontier across (performance, -cost, -risk, stability, business)
        pareto_ids = self._compute_pareto_frontier(results)
        for r in results:
            r.is_pareto_optimal = r.action_id in pareto_ids

        elapsed = time.monotonic() - start
        logger.info(
            "simulate.complete",
            cycle_id=cycle_id,
            total_scenarios=total_scenarios,
            pareto_size=len(pareto_ids),
            elapsed_ms=round(elapsed * 1000, 1),
        )

        return SimulationSuite(
            timestamp=datetime.now(timezone.utc),
            cycle_id=cycle_id,
            n_actions_evaluated=len(results),
            n_pareto_optimal=len(pareto_ids),
            results=results,
            pareto_frontier=pareto_ids,
            simulation_time_ms=round(elapsed * 1000, 1),
        )

    # ------------------------------------------------------------------
    # Per-action simulation
    # ------------------------------------------------------------------

    def _simulate_action(
        self,
        base_state: dict[str, float],
        action: ActionCandidate,
        n_scenarios: int,
        volatility: dict[str, float],
    ) -> SimulationResult:
        """Run N Monte Carlo scenarios for a single action."""
        scenario_results: list[ScenarioResult] = []
        objective_values: list[float] = []
        sla_breaches = 0

        # Target state after action effect
        target_state = self._apply_action_effect(dict(base_state), action)

        for i in range(n_scenarios):
            trajectory = self._evolve_sde(
                state=dict(base_state),
                target=target_state,
                n_steps=_N_STEPS,
                dt=_DT,
                volatility=volatility,
            )

            terminal = trajectory[-1] if trajectory else target_state
            obj_value = self._evaluate_objective(trajectory, action)
            sla_ok = self._check_sla(terminal)

            if not sla_ok:
                sla_breaches += 1

            objective_values.append(obj_value)
            cost_init = base_state.get("cloud_spend_rate", 1.0)
            cost_term = terminal.get("cloud_spend_rate", cost_init)
            sc_cost_delta = float(cost_term - cost_init)

            scenario_results.append(ScenarioResult(
                scenario_id=i,
                trajectory=trajectory,
                objective_value=round(obj_value, 4),
                sla_compliant=sla_ok,
                cost_delta=round(sc_cost_delta, 4),
                final_state={k: round(v, 4) for k, v in terminal.items()},
            ))

        obj_arr = np.array(objective_values)
        var_95 = float(np.percentile(obj_arr, 5)) if len(obj_arr) > 0 else 0.0
        cvar_95 = compute_cvar(objective_values, alpha=0.05)

        # Objective component breakdown (from the mean terminal state)
        mean_terminal = self._mean_dict(
            [sr.final_state for sr in scenario_results]
        )
        # Compute cost delta from scenario results
        cost_deltas = [sr.cost_delta for sr in scenario_results]
        expected_cost = float(np.mean(cost_deltas)) if cost_deltas else 0.0

        # Compute latency/error reduction from mean terminal vs base
        lat_base = base_state.get("latency_p99", 500.0)
        lat_term = mean_terminal.get("latency_p99", lat_base)
        latency_reduction = max(0.0, lat_base - lat_term)

        err_base = base_state.get("error_rate_5xx", 1.0)
        err_term = mean_terminal.get("error_rate_5xx", err_base)
        error_reduction = max(0.0, err_base - err_term)

        # Stability = negative std of objective (lower variance = more stable)
        obj_std = float(np.std(obj_arr, ddof=1)) if len(obj_arr) > 1 else 0.0

        return SimulationResult(
            action_id=action.id,
            action_description=action.description,
            n_scenarios=n_scenarios,
            expected_objective=round(float(np.mean(obj_arr)), 4),
            var_alpha=round(var_95, 4),
            cvar_alpha=round(cvar_95, 4),
            sla_breach_probability=round(sla_breaches / max(n_scenarios, 1), 4),
            expected_cost_delta=round(expected_cost, 4),
            mean_latency_reduction=round(latency_reduction, 2),
            mean_error_rate_reduction=round(error_reduction, 4),
            stability_score=round(1.0 / (1.0 + obj_std), 4),
            is_pareto_optimal=False,  # set later by _compute_pareto_frontier
        )

    # ------------------------------------------------------------------
    # Action effect modelling
    # ------------------------------------------------------------------

    def _apply_action_effect(self, state: dict[str, float], action: ActionCandidate) -> dict[str, float]:
        """Model how an action changes the system state (returns target state)."""
        s = dict(state)
        params = action.parameters

        if action.type == ActionType.HORIZONTAL_SCALE:
            current_replicas = params.get("current_replicas", 3)
            add_replicas = params.get("add_replicas", 1)
            new_replicas = current_replicas + add_replicas
            scale_factor = current_replicas / new_replicas

            s["cpu_usage"] = s.get("cpu_usage", 50) * scale_factor
            s["memory_usage"] = s.get("memory_usage", 50) * scale_factor
            s["latency_p50"] = s.get("latency_p50", 50) * (0.7 + 0.3 * scale_factor)
            s["latency_p95"] = s.get("latency_p95", 120) * (0.7 + 0.3 * scale_factor)
            s["latency_p99"] = s.get("latency_p99", 280) * (0.7 + 0.3 * scale_factor)
            s["connection_pool_utilization"] = s.get("connection_pool_utilization", 60) * scale_factor
            s["cloud_spend_rate_hr"] = s.get("cloud_spend_rate_hr", 40) * (new_replicas / current_replicas)

        elif action.type == ActionType.RATE_LIMIT:
            limit_rps = params.get("limit_rps", 500)
            current_rps = s.get("request_rate", 800)
            if current_rps > limit_rps:
                reduction_factor = limit_rps / current_rps
                s["request_rate"] = limit_rps
                s["latency_p50"] = s.get("latency_p50", 50) * (0.5 + 0.5 * reduction_factor)
                s["latency_p95"] = s.get("latency_p95", 120) * (0.5 + 0.5 * reduction_factor)
                s["latency_p99"] = s.get("latency_p99", 280) * (0.5 + 0.5 * reduction_factor)
                s["cpu_usage"] = s.get("cpu_usage", 50) * (0.6 + 0.4 * reduction_factor)
                s["error_rate_4xx"] = s.get("error_rate_4xx", 1) + (1 - reduction_factor) * 100 * 0.05

        elif action.type == ActionType.CIRCUIT_BREAK:
            target_service = params.get("target_service", "")
            s["error_rate_5xx"] = s.get("error_rate_5xx", 2) * 0.3
            s["circuit_breaker_open_pct"] = min(100, s.get("circuit_breaker_open_pct", 0) + 15)
            s["latency_p99"] = s.get("latency_p99", 280) * 0.6
            s["inter_service_latency_ms"] = s.get("inter_service_latency_ms", 8) * 0.5

        elif action.type == ActionType.TRAFFIC_SHIFT:
            shift_pct = params.get("shift_percentage", 20) / 100.0
            s["request_rate"] = s.get("request_rate", 800) * (1 - shift_pct)
            s["cpu_usage"] = s.get("cpu_usage", 50) * (1 - shift_pct * 0.3)
            s["latency_p99"] = s.get("latency_p99", 280) * (1 - shift_pct * 0.4)

        elif action.type == ActionType.VERTICAL_SCALE:
            cpu_add_pct = params.get("cpu_increase_pct", 50) / 100.0
            mem_add_pct = params.get("memory_increase_pct", 50) / 100.0
            s["cpu_usage"] = s.get("cpu_usage", 50) / (1 + cpu_add_pct)
            s["memory_usage"] = s.get("memory_usage", 50) / (1 + mem_add_pct)
            s["cloud_spend_rate_hr"] = s.get("cloud_spend_rate_hr", 40) * (1 + (cpu_add_pct + mem_add_pct) * 0.3)

        elif action.type == ActionType.NOOP:
            pass  # no changes

        # Clamp values to valid ranges
        for key in ("cpu_usage", "memory_usage", "connection_pool_utilization",
                     "reserved_utilization_pct", "sla_compliance", "circuit_breaker_open_pct",
                     "error_rate_4xx", "error_rate_5xx", "node_health"):
            if key in s:
                s[key] = max(0.0, min(100.0, s[key]))

        for key in ("latency_p50", "latency_p95", "latency_p99", "request_rate",
                     "cloud_spend_rate_hr", "inter_service_latency_ms", "queue_depth"):
            if key in s:
                s[key] = max(0.0, s[key])

        return s

    # ------------------------------------------------------------------
    # SDE evolution (Euler-Maruyama)
    # ------------------------------------------------------------------

    def _evolve_sde(
        self,
        state: dict[str, float],
        target: dict[str, float],
        n_steps: int,
        dt: float,
        volatility: dict[str, float],
    ) -> list[dict[str, float]]:
        """Simplified Euler-Maruyama SDE evolution.

        dS = theta * (mu - S) * dt + sigma * sqrt(dt) * dW

        where:
            theta = mean-reversion speed
            mu    = target state (post-action equilibrium)
            sigma = noise scale from historical volatility
        """
        trajectory: list[dict[str, float]] = [dict(state)]
        current = dict(state)
        sqrt_dt = np.sqrt(dt)

        for _ in range(n_steps):
            next_state: dict[str, float] = {}
            for key, val in current.items():
                mu = target.get(key, val)
                sigma = volatility.get(key, abs(val) * 0.02)

                # Ornstein-Uhlenbeck step
                drift = _THETA * (mu - val) * dt
                diffusion = sigma * sqrt_dt * self._rng.standard_normal()
                new_val = val + drift + diffusion

                # Clamp non-negative metrics
                if key in ("cpu_usage", "memory_usage", "latency_p50", "latency_p95",
                           "latency_p99", "request_rate", "error_rate_4xx", "error_rate_5xx",
                           "queue_depth", "cloud_spend_rate_hr"):
                    new_val = max(0.0, new_val)
                # Clamp percentages
                if key.endswith("_pct") or key in ("cpu_usage", "memory_usage",
                                                     "connection_pool_utilization",
                                                     "sla_compliance", "node_health"):
                    new_val = min(100.0, new_val)

                next_state[key] = new_val

            trajectory.append(next_state)
            current = next_state

        return trajectory

    # ------------------------------------------------------------------
    # Objective evaluation
    # ------------------------------------------------------------------

    def _evaluate_objective(self, trajectory: list[dict[str, float]], action: ActionCandidate) -> float:
        """Multi-objective evaluation: performance + cost + risk + stability + business."""
        if not trajectory or len(trajectory) < 2:
            return 0.0

        initial = trajectory[0]
        terminal = trajectory[-1]

        # Performance: latency improvement (positive = better)
        lat_init = initial.get("latency_p99", 200)
        lat_term = terminal.get("latency_p99", 200)
        perf = (lat_init - lat_term) / max(lat_init, 1.0)

        # Cost: negative of cost increase (lower cost = better)
        cost_init = initial.get("cloud_spend_rate_hr", 40)
        cost_term = terminal.get("cloud_spend_rate_hr", 40)
        cost_delta = -(cost_term - cost_init) / max(cost_init, 1.0)

        # Risk: tail risk from trajectory variance
        p99_values = [step.get("latency_p99", 200) for step in trajectory]
        tail_risk = -float(np.std(p99_values)) / max(lat_init, 1.0) if len(p99_values) > 1 else 0.0

        # Stability: negative variance of key metrics across trajectory
        stab_metrics = ["cpu_usage", "memory_usage", "error_rate_5xx"]
        stability = 0.0
        for m in stab_metrics:
            vals = [step.get(m, 0) for step in trajectory]
            if vals:
                stability -= float(np.std(vals)) / max(abs(np.mean(vals)), 1.0)
        stability /= len(stab_metrics)

        # Business: SLA margin improvement
        sla_init = initial.get("sla_compliance", 99)
        sla_term = terminal.get("sla_compliance", 99)
        biz = (sla_term - sla_init) / max(100 - sla_init, 0.1)

        objective = (
            _W_PERF * perf
            + _W_COST * cost_delta
            + _W_RISK * tail_risk
            + _W_STAB * stability
            + _W_BIZ * biz
        )
        return objective

    def _objective_components(
        self,
        terminal: dict[str, float],
        initial: dict[str, float],
        action: ActionCandidate,
    ) -> dict[str, float]:
        """Break down objective into named components."""
        lat_i = initial.get("latency_p99", 200)
        lat_t = terminal.get("latency_p99", 200)
        cost_i = initial.get("cloud_spend_rate_hr", 40)
        cost_t = terminal.get("cloud_spend_rate_hr", 40)
        sla_i = initial.get("sla_compliance", 99)
        sla_t = terminal.get("sla_compliance", 99)

        return {
            "performance": round((lat_i - lat_t) / max(lat_i, 1.0), 4),
            "cost": round(-(cost_t - cost_i) / max(cost_i, 1.0), 4),
            "risk": 0.0,  # risk is trajectory-dependent, not terminal
            "stability": 0.0,
            "business": round((sla_t - sla_i) / max(100 - sla_i, 0.1), 4),
        }

    # ------------------------------------------------------------------
    # SLA compliance
    # ------------------------------------------------------------------

    @staticmethod
    def _check_sla(state: dict[str, float]) -> bool:
        """Check if a state snapshot meets SLA constraints."""
        p99 = state.get("latency_p99", 0)
        err = state.get("error_rate_5xx", 0)
        return p99 <= _SLA_P99_LIMIT_MS and err <= _SLA_ERROR_LIMIT_PCT

    # ------------------------------------------------------------------
    # Pareto frontier
    # ------------------------------------------------------------------

    def _compute_pareto_frontier(self, results: list[SimulationResult]) -> list[str]:
        """Find Pareto-optimal action IDs across objective components."""
        if not results:
            return []

        action_ids = [r.action_id for r in results]
        objectives = [
            [
                r.expected_objective,
                -r.expected_cost_delta,
                r.mean_latency_reduction,
                -r.sla_breach_probability,
                -r.cvar_alpha,
            ]
            for r in results
        ]

        # All objectives are "higher is better" after negation above,
        # so minimize=False for all
        pareto_indices = compute_pareto_frontier(
            objectives,
            minimize=[False, False, False, False, False],
        )

        return [action_ids[i] for i in pareto_indices]

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _state_to_dict(state: SystemState) -> dict[str, float]:
        """Flatten a SystemState into a metric-name->value dict."""
        out: dict[str, float] = {}
        for vec in (state.infrastructure, state.application, state.business, state.network, state.cost):
            for m in vec.metrics:
                out[m.name] = m.value
        return out

    def _estimate_volatility(self, state: SystemState) -> dict[str, float]:
        """Estimate per-metric volatility from derived analytics."""
        vol: dict[str, float] = {}
        state_dict = self._state_to_dict(state)

        for tv in state.derived.trend_vectors:
            # Use the magnitude of short-term trend as volatility proxy
            base = abs(state_dict.get(tv.metric_name, 1.0))
            trend_mag = max(abs(tv.delta_5min), abs(tv.delta_15min))
            vol[tv.metric_name] = max(base * 0.01, trend_mag * 2.0)

        # Ensure every metric has some volatility estimate
        for name, val in state_dict.items():
            if name not in vol:
                vol[name] = max(abs(val) * 0.02, 0.01)

        return vol

    @staticmethod
    def _mean_dict(dicts: list[dict[str, float]]) -> dict[str, float]:
        """Compute element-wise mean across a list of dicts."""
        if not dicts:
            return {}
        keys = dicts[0].keys()
        result: dict[str, float] = {}
        for k in keys:
            vals = [d.get(k, 0.0) for d in dicts]
            result[k] = round(float(np.mean(vals)), 4)
        return result
