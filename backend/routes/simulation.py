"""Simulation API routes.

Endpoints for retrieving the latest simulation results, running ad-hoc
simulations with custom action candidates, and getting Pareto frontier
visualisation data.
"""

from __future__ import annotations

import time
from datetime import datetime, timezone
from typing import Any
from uuid import uuid4

import numpy as np
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from config import get_settings
from core.shared import get_governor
from models.action import ActionCandidate
from models.simulation import SimulationResult, SimulationSuite
from phases.simulate import SimulatePhase
from utils.logger import get_logger
from utils.statistics import compute_cvar

router = APIRouter(prefix="/simulation", tags=["simulation"])
log = get_logger(__name__)


class SimulationRequest(BaseModel):
    """Request body for an ad-hoc simulation run."""

    actions: list[ActionCandidate]
    n_scenarios: int = 100


# ------------------------------------------------------------------
# Endpoints
# ------------------------------------------------------------------


@router.get("/latest")
async def get_latest_simulation() -> dict[str, Any]:
    """Return the most recent simulation results from the governor's cycle history."""
    gov = get_governor()

    # Walk backward through cycle outputs to find one with simulation data
    for output in reversed(gov.cycle_outputs):
        sim = output.simulation_results
        if isinstance(sim, dict) and sim.get("status") not in ("error", "skipped", None):
            return sim
        if isinstance(sim, dict) and "results" in sim:
            return sim

    return {"status": "no_data", "message": "No simulation results available yet."}


@router.post("/run")
async def run_simulation(req: SimulationRequest) -> dict[str, Any]:
    """Run a simulation with custom action candidates.

    Uses the latest system state from the governor and the provided
    actions to run Monte Carlo scenarios.
    """
    gov = get_governor()
    settings = get_settings()

    if not gov.state_history:
        raise HTTPException(
            status_code=400,
            detail="No system state available. Run at least one observe cycle first.",
        )

    state = gov.state_history[-1]

    # Get a prediction if available, otherwise use a dummy
    prediction = None
    for output in reversed(gov.cycle_outputs):
        pred = output.prediction
        if isinstance(pred, dict) and pred.get("status") not in ("error", "skipped"):
            # Reconstruct a minimal prediction object
            from models.prediction import PredictionOutput, RiskAssessment

            prediction = PredictionOutput(
                timestamp=datetime.now(timezone.utc),
                cycle_id=f"adhoc-{uuid4().hex[:8]}",
                horizons=[],
                risk_assessment=RiskAssessment(),
            )
            break

    if prediction is None:
        from models.prediction import PredictionOutput, RiskAssessment

        prediction = PredictionOutput(
            timestamp=datetime.now(timezone.utc),
            cycle_id=f"adhoc-{uuid4().hex[:8]}",
            horizons=[],
            risk_assessment=RiskAssessment(),
        )

    # Run simulation
    simulate_phase = SimulatePhase(settings)
    simulate_phase.n_scenarios = min(req.n_scenarios, settings.SIMULATION_SCENARIOS)

    cycle_id = f"adhoc-sim-{uuid4().hex[:8]}"
    suite = await simulate_phase.execute(state, prediction, req.actions, cycle_id)

    return suite.model_dump(mode="json") if hasattr(suite, "model_dump") else {}


@router.get("/pareto")
async def get_pareto_frontier() -> dict[str, Any]:
    """Return Pareto frontier visualisation data from the latest simulation.

    Returns the Pareto-optimal action IDs and their objective components
    so the frontend can render a scatter plot or parallel coordinates view.
    """
    gov = get_governor()

    # Find the latest simulation with results
    sim_data: dict[str, Any] | None = None
    for output in reversed(gov.cycle_outputs):
        sim = output.simulation_results
        if isinstance(sim, dict) and "results" in sim:
            sim_data = sim
            break

    if sim_data is None:
        return {
            "status": "no_data",
            "message": "No simulation results available for Pareto analysis.",
        }

    results = sim_data.get("results", [])
    pareto_ids = sim_data.get("pareto_frontier", [])

    # Build visualisation-friendly data
    points: list[dict[str, Any]] = []
    for r in results:
        if isinstance(r, dict):
            point = {
                "action_id": r.get("action_id", "?"),
                "action_description": r.get("action_description", ""),
                "expected_objective": r.get("expected_objective", 0),
                "sla_breach_probability": r.get("sla_breach_probability", 0),
                "cvar_alpha": r.get("cvar_alpha", 0),
                "expected_cost_delta": r.get("expected_cost_delta", 0),
                "is_pareto": r.get("action_id", "") in pareto_ids,
            }
            points.append(point)

    return {
        "pareto_frontier": pareto_ids,
        "n_total": len(results),
        "n_pareto": len(pareto_ids),
        "points": points,
    }
