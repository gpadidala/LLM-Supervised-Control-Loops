"""Governor control-loop API routes.

Endpoints for starting/stopping the control loop, triggering manual cycles,
and retrieving cycle history.  All endpoints operate on the shared
SCLGovernor singleton.
"""

from __future__ import annotations

import asyncio
from typing import Any

from fastapi import APIRouter, BackgroundTasks, HTTPException

from core.shared import get_governor
from models.decision import ControlCycleOutput
from utils.logger import get_logger

router = APIRouter(prefix="/governor", tags=["governor"])
log = get_logger(__name__)


@router.get("/status")
async def governor_status() -> dict[str, Any]:
    """Return the current governor status (is_running, cycle_count, current_regime, etc.)."""
    gov = get_governor()
    return gov.get_status()


@router.post("/start")
async def start_loop(background_tasks: BackgroundTasks) -> dict[str, str]:
    """Start the SCL control loop running in a background task."""
    gov = get_governor()
    if gov.is_running:
        raise HTTPException(status_code=409, detail="Control loop is already running")
    background_tasks.add_task(gov.start)
    log.info("control_loop_start_requested")
    return {"status": "starting"}


@router.post("/stop")
async def stop_loop() -> dict[str, str]:
    """Stop the SCL control loop after the current cycle completes."""
    gov = get_governor()
    if not gov.is_running:
        raise HTTPException(status_code=409, detail="Control loop is not running")
    gov.stop()
    log.info("control_loop_stop_requested")
    return {"status": "stopping"}


@router.post("/cycle")
async def trigger_cycle() -> dict[str, Any]:
    """Trigger a single manual control cycle and return the output."""
    gov = get_governor()
    log.info("manual_cycle_requested")
    output = await gov.run_cycle()
    return output.model_dump(mode="json")


@router.get("/cycles")
async def list_cycles(limit: int = 20) -> list[dict[str, Any]]:
    """Return recent cycle outputs, newest first."""
    gov = get_governor()
    cycles = gov.get_recent_cycles(n=limit)
    return [c.model_dump(mode="json") for c in cycles]


@router.get("/cycles/{cycle_id}")
async def get_cycle(cycle_id: str) -> dict[str, Any]:
    """Return a specific cycle output by ID."""
    gov = get_governor()
    output = gov.get_cycle_by_id(cycle_id)
    if output is None:
        raise HTTPException(status_code=404, detail=f"Cycle {cycle_id} not found")
    return output.model_dump(mode="json")
