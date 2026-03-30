"""Pydantic models for the SCL-Governor simulation phase.

Simulation evaluates each candidate action by running Monte Carlo scenarios
and produces risk-adjusted metrics (VaR, CVaR, Pareto optimality).
"""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel


class ScenarioResult(BaseModel):
    """Outcome of a single Monte Carlo scenario for one action."""

    scenario_id: int
    trajectory: list[dict[str, float]]  # time-indexed metric snapshots
    objective_value: float
    sla_compliant: bool
    cost_delta: float
    final_state: dict[str, float] = {}


class SimulationResult(BaseModel):
    """Aggregated simulation statistics for one candidate action."""

    action_id: str
    action_description: str
    n_scenarios: int
    expected_objective: float  # E[J]
    var_alpha: float  # Value-at-Risk
    cvar_alpha: float  # Conditional VaR (tail risk)
    sla_breach_probability: float
    expected_cost_delta: float
    mean_latency_reduction: float = 0.0
    mean_error_rate_reduction: float = 0.0
    stability_score: float = 0.0  # variance of trajectories
    is_pareto_optimal: bool = False


class SimulationSuite(BaseModel):
    """Complete simulation output for one control cycle."""

    timestamp: datetime
    cycle_id: str
    n_actions_evaluated: int
    n_pareto_optimal: int
    results: list[SimulationResult]
    pareto_frontier: list[str]  # action IDs on the Pareto front
    simulation_time_ms: float
