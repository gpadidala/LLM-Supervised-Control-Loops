"""Decision API routes.

Endpoints for viewing the decision audit log, inspecting individual
decisions with full reasoning, submitting human overrides, and
querying decision statistics.
"""

from __future__ import annotations

from collections import Counter
from datetime import datetime, timezone
from typing import Any

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from core.shared import get_governor
from utils.logger import get_logger

router = APIRouter(prefix="/decisions", tags=["decisions"])
log = get_logger(__name__)


class OverrideRequest(BaseModel):
    """Payload for submitting a human override / feedback for a decision."""

    decision_cycle_id: str
    approved: bool
    operator_notes: str = ""
    corrected_action_id: str | None = None


# ------------------------------------------------------------------
# Endpoints -- fixed-path routes MUST come before /{decision_id}
# ------------------------------------------------------------------


@router.get("/")
async def list_decisions(limit: int = 50) -> list[dict[str, Any]]:
    """Return recent decisions from the audit log, newest first."""
    gov = get_governor()
    entries = list(gov.decision_history)[-limit:]
    entries.reverse()
    result: list[dict[str, Any]] = []
    for entry in entries:
        decision = entry.get("decision")
        execution = entry.get("execution")
        item: dict[str, Any] = {}
        if hasattr(decision, "model_dump"):
            item["decision"] = decision.model_dump(mode="json")
        elif isinstance(decision, dict):
            item["decision"] = decision
        if hasattr(execution, "model_dump"):
            item["execution"] = execution.model_dump(mode="json")
        elif isinstance(execution, dict):
            item["execution"] = execution
        result.append(item)
    return result


@router.get("/stats")
async def decision_stats() -> dict[str, Any]:
    """Return decision statistics: autonomy level distribution, confidence distribution."""
    gov = get_governor()

    autonomy_counts: Counter[str] = Counter()
    confidence_buckets: Counter[str] = Counter()
    total = 0

    for entry in gov.decision_history:
        decision = entry.get("decision")
        if decision is None:
            continue
        total += 1

        # Autonomy level
        autonomy = getattr(decision, "autonomy_level", None)
        if autonomy is not None:
            level_str = autonomy.value if hasattr(autonomy, "value") else str(autonomy)
            autonomy_counts[level_str] += 1
        elif isinstance(decision, dict):
            autonomy_counts[decision.get("autonomy_level", "unknown")] += 1

        # Confidence bucket
        confidence = getattr(decision, "confidence", None)
        if confidence is None and isinstance(decision, dict):
            confidence = decision.get("confidence")
        if confidence is not None:
            try:
                c = float(confidence)
                if c >= 0.85:
                    confidence_buckets["high (>=0.85)"] += 1
                elif c >= 0.65:
                    confidence_buckets["medium (0.65-0.85)"] += 1
                elif c >= 0.40:
                    confidence_buckets["low (0.40-0.65)"] += 1
                else:
                    confidence_buckets["very_low (<0.40)"] += 1
            except (ValueError, TypeError):
                pass

    return {
        "total_decisions": total,
        "autonomy_distribution": dict(autonomy_counts),
        "confidence_distribution": dict(confidence_buckets),
        "human_overrides": len(gov.overrides),
    }


@router.post("/override")
async def submit_override(req: OverrideRequest) -> dict[str, str]:
    """Submit a human override or feedback for a decision.

    This stores the feedback for the learn phase to incorporate in
    future cycles.
    """
    gov = get_governor()

    # Verify the decision exists
    found = False
    for entry in gov.decision_history:
        decision = entry.get("decision")
        cid = getattr(decision, "cycle_id", None)
        if cid is None and isinstance(decision, dict):
            cid = decision.get("cycle_id")
        if cid == req.decision_cycle_id:
            found = True
            break

    if not found:
        raise HTTPException(
            status_code=404,
            detail=f"Decision {req.decision_cycle_id} not found",
        )

    override_record = {
        "decision_cycle_id": req.decision_cycle_id,
        "approved": req.approved,
        "operator_notes": req.operator_notes,
        "corrected_action_id": req.corrected_action_id,
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }
    gov.overrides.append(override_record)

    log.info(
        "human_override_submitted",
        decision_id=req.decision_cycle_id,
        approved=req.approved,
    )
    return {"status": "recorded", "decision_cycle_id": req.decision_cycle_id}


@router.get("/{decision_id}")
async def get_decision(decision_id: str) -> dict[str, Any]:
    """Return a specific decision with full reasoning by cycle_id."""
    gov = get_governor()
    for entry in reversed(gov.decision_history):
        decision = entry.get("decision")
        cid = getattr(decision, "cycle_id", None)
        if cid is None and isinstance(decision, dict):
            cid = decision.get("cycle_id")
        if cid == decision_id:
            result: dict[str, Any] = {}
            if hasattr(decision, "model_dump"):
                result["decision"] = decision.model_dump(mode="json")
            elif isinstance(decision, dict):
                result["decision"] = decision
            execution = entry.get("execution")
            if hasattr(execution, "model_dump"):
                result["execution"] = execution.model_dump(mode="json")
            elif isinstance(execution, dict):
                result["execution"] = execution
            return result
    raise HTTPException(status_code=404, detail=f"Decision {decision_id} not found")
