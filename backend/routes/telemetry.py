"""Telemetry API routes.

Endpoints for querying the current system state, state history,
available metric names, and detected anomalies.  Reads from the
shared governor's state history.
"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, HTTPException, Query

from core.shared import get_governor
from utils.logger import get_logger

router = APIRouter(prefix="/telemetry", tags=["telemetry"])
log = get_logger(__name__)


@router.get("/current")
async def get_current_state() -> dict[str, Any]:
    """Return the latest system state from the governor's history.

    If no state has been recorded yet, returns a placeholder response.
    """
    gov = get_governor()
    if not gov.state_history:
        return {
            "status": "no_data",
            "message": "No system state recorded yet. Run a cycle first.",
        }
    state = gov.state_history[-1]
    return state.model_dump(mode="json")


@router.get("/history")
async def get_state_history(
    limit: int = Query(default=50, ge=1, le=1000),
    metric_name: str | None = Query(default=None),
) -> list[dict[str, Any]]:
    """Return state history, newest first.

    If ``metric_name`` is provided, return only the timeseries for that
    metric across all recorded states.
    """
    gov = get_governor()
    states = list(gov.state_history)[-limit:]
    states.reverse()

    if metric_name:
        # Extract a specific metric timeseries
        timeseries: list[dict[str, Any]] = []
        for st in states:
            for vec in (
                st.infrastructure,
                st.application,
                st.business,
                st.network,
                st.cost,
            ):
                for m in vec.metrics:
                    if m.name == metric_name:
                        timeseries.append(
                            {
                                "cycle_id": st.cycle_id,
                                "timestamp": st.timestamp.isoformat(),
                                "name": m.name,
                                "value": m.value,
                                "unit": m.unit,
                                "labels": m.labels,
                            }
                        )
        return timeseries

    return [s.model_dump(mode="json") for s in states]


@router.get("/metrics")
async def list_metric_names() -> list[str]:
    """Return all unique metric names observed so far."""
    gov = get_governor()
    names: set[str] = set()
    for st in gov.state_history:
        for vec in (
            st.infrastructure,
            st.application,
            st.business,
            st.network,
            st.cost,
        ):
            for m in vec.metrics:
                names.add(m.name)
    return sorted(names)


@router.get("/anomalies")
async def get_anomalies() -> list[dict[str, Any]]:
    """Return current anomalies from the latest system state."""
    gov = get_governor()
    if not gov.state_history:
        return []

    state = gov.state_history[-1]
    anomalies: list[dict[str, Any]] = []
    for a in state.derived.anomaly_scores:
        if a.is_anomalous:
            anomalies.append(
                {
                    "metric_name": a.metric_name,
                    "z_score": a.z_score,
                    "mad_score": a.mad_score,
                    "is_anomalous": a.is_anomalous,
                    "causal_attribution": a.causal_attribution,
                    "cycle_id": state.cycle_id,
                    "timestamp": state.timestamp.isoformat(),
                }
            )
    return anomalies
