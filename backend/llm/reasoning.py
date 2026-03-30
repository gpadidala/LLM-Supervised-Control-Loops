"""Prompt engineering and response parsing for SCL-Governor LLM integration."""

from __future__ import annotations

import json
import re
from typing import Any

from models.state import SystemState

# ---------------------------------------------------------------------------
# System prompt
# ---------------------------------------------------------------------------

SCL_SYSTEM_PROMPT = (
    "You are SCL-Governor's reasoning engine -- an expert Site Reliability "
    "Engineer embedded inside an autonomous control loop for distributed systems.\n\n"
    "Your role is to analyse system telemetry, predict future states, and "
    "recommend or decide on corrective actions while respecting safety constraints.\n\n"
    "Key principles:\n"
    "1. SAFETY FIRST: Never recommend an action whose blast radius exceeds "
    "the configured maximum.  Prefer reversible actions.\n"
    "2. EVIDENCE-BASED: Ground every recommendation in the metrics and trends "
    "you are given.  Cite specific metric values.\n"
    "3. PROPORTIONAL: Match the severity of the response to the severity of "
    "the issue.  Do not over-react to transient spikes.\n"
    "4. EXPLAIN: Provide concise but complete reasoning so human operators "
    "can audit your decisions.\n"
    "5. UNCERTAINTY: When you are uncertain, say so.  Lower your confidence "
    "score accordingly and recommend human review.\n\n"
    "When asked for a decision, respond with a JSON block containing:\n"
    '- "selected_action_id": the ID of the chosen action candidate\n'
    '- "reasoning": a 2-4 sentence explanation\n'
    '- "confidence": a float between 0 and 1\n'
    '- "risk_factors": a list of risk strings\n'
    '- "rollback_plan": how to undo the action\n'
    '- "rollback_trigger": what metric condition should trigger auto-rollback\n\n'
    "When asked for causal analysis, respond with a JSON block containing:\n"
    '- "causal_insights": a list of causal relationship strings\n'
    '- "risk_assessment": { "sla_breach_probability", "cascading_failure_probability", '
    '"cost_overrun_probability" }\n'
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _flatten_state_metrics(state: SystemState) -> dict[str, float]:
    """Flatten a SystemState into a name->value dict using its telemetry vectors."""
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


# ---------------------------------------------------------------------------
# Prompt builders
# ---------------------------------------------------------------------------


def build_prediction_prompt(
    state: SystemState,
    forecasts: list[dict[str, Any]],
) -> str:
    """Build a prompt for causal analysis during the prediction phase.

    Provides the LLM with the current metric snapshot and any statistical
    forecasts so it can identify causal relationships and assess risk.
    """
    flat = _flatten_state_metrics(state)

    # Summarise top metrics
    metric_lines: list[str] = []
    for name, value in sorted(flat.items()):
        metric_lines.append(f"  {name}: {value:.4f}")
    metrics_block = "\n".join(metric_lines) if metric_lines else "  (no metrics available)"

    # Summarise anomalies
    anomaly_lines: list[str] = []
    for a in state.derived.anomaly_scores:
        if a.is_anomalous:
            anomaly_lines.append(f"  {a.metric_name} (MAD score={a.mad_score:.2f})")
    anomaly_block = "\n".join(anomaly_lines) if anomaly_lines else "  (none)"

    # Summarise trends
    trend_lines: list[str] = []
    for t in state.derived.trend_vectors:
        # Consider non-zero deltas as noteworthy
        if abs(t.delta_5min) > 0.001 or abs(t.delta_15min) > 0.001:
            trend_lines.append(
                f"  {t.metric_name}: "
                f"5m={t.delta_5min:+.4f}, 15m={t.delta_15min:+.4f}, 1h={t.delta_1hr:+.4f}"
            )
    trend_block = "\n".join(trend_lines) if trend_lines else "  (all stable)"

    # Summarise forecasts
    forecast_lines: list[str] = []
    for f in forecasts:
        forecast_lines.append(
            f"  horizon={f.get('horizon_seconds', '?')}s: "
            f"{json.dumps(f, default=str)[:200]}"
        )
    forecast_block = "\n".join(forecast_lines) if forecast_lines else "  (none)"

    return (
        "Analyse the current system state and provide causal insights "
        "and a risk assessment.\n\n"
        f"## Current Metrics\n{metrics_block}\n\n"
        f"## Anomalies Detected\n{anomaly_block}\n\n"
        f"## Metric Trends\n{trend_block}\n\n"
        f"## Statistical Forecasts\n{forecast_block}\n\n"
        f"## Regime\n  {state.regime}\n\n"
        "Respond ONLY with a JSON object containing "
        '"causal_insights" (list of strings) and "risk_assessment" '
        "(object with sla_breach_probability, cascading_failure_probability, "
        "cost_overrun_probability).\n"
    )


def build_decision_prompt(
    state: SystemState,
    candidates: list[dict[str, Any]],
    simulations: dict[str, Any],
) -> str:
    """Build a prompt for action selection during the decision phase.

    Presents the LLM with system state, candidate actions, and their
    simulation outcomes so it can pick the best action.
    """
    flat = _flatten_state_metrics(state)

    metric_lines = [f"  {k}: {v:.4f}" for k, v in sorted(flat.items())]
    metrics_block = "\n".join(metric_lines) if metric_lines else "  (no metrics)"

    # Format candidates
    candidate_lines: list[str] = []
    for c in candidates:
        cid = c.get("id", c.get("action_id", "?"))
        ctype = c.get("type", c.get("action_type", "?"))
        target = c.get("target_service", c.get("target", "?"))
        blast = c.get("blast_radius", 0)
        desc = c.get("description", "")
        candidate_lines.append(
            f"  - [{cid}] {ctype} on {target} (blast_radius={blast:.2f}): {desc}"
        )
    candidates_block = "\n".join(candidate_lines) if candidate_lines else "  (none)"

    # Format simulation results
    sim_lines: list[str] = []
    for action_id, sim in simulations.items():
        if isinstance(sim, dict):
            exp = sim.get("expected_objective", "?")
            breach = sim.get("sla_breach_probability", "?")
            sim_lines.append(
                f"  - [{action_id}] expected_objective={exp}, sla_breach_prob={breach}"
            )
    sim_block = "\n".join(sim_lines) if sim_lines else "  (no simulation data)"

    return (
        "Select the best action for the current system state.\n\n"
        f"## Current Metrics\n{metrics_block}\n\n"
        f"## Regime: {state.regime}\n\n"
        f"## Candidate Actions\n{candidates_block}\n\n"
        f"## Simulation Results\n{sim_block}\n\n"
        "Select the best action.  Respond ONLY with a JSON object:\n"
        "{\n"
        '  "selected_action_id": "<action_id>",\n'
        '  "reasoning": "<2-4 sentences>",\n'
        '  "confidence": <0.0-1.0>,\n'
        '  "risk_factors": ["..."],\n'
        '  "rollback_plan": "<how to undo>",\n'
        '  "rollback_trigger": "<metric condition>"\n'
        "}\n"
    )


# ---------------------------------------------------------------------------
# Response parsing
# ---------------------------------------------------------------------------


def parse_decision_response(response: str) -> tuple[str, str, float]:
    """Parse the LLM's decision response.

    Returns ``(action_id, reasoning, confidence)``.
    Falls back to ``("noop", "<raw response>", 0.0)`` on parse failure.
    """
    if not response:
        return ("noop", "No LLM response received", 0.0)

    # Try to extract JSON block from the response
    json_match = re.search(r"\{[\s\S]*\}", response)
    if json_match:
        try:
            data = json.loads(json_match.group())
            action_id = data.get("selected_action_id", "noop")
            reasoning = data.get("reasoning", "")
            confidence = float(data.get("confidence", 0.0))
            # Clamp confidence to [0, 1]
            confidence = max(0.0, min(1.0, confidence))
            return (action_id, reasoning, confidence)
        except (json.JSONDecodeError, ValueError, TypeError):
            pass

    # Fallback: could not parse structured response
    return ("noop", f"Could not parse LLM response: {response[:300]}", 0.0)


def parse_causal_response(response: str) -> dict[str, Any]:
    """Parse the LLM's causal analysis response.

    Returns a dict with ``causal_insights`` (list) and ``risk_assessment``
    (dict) keys.  Falls back to empty defaults on parse failure.
    """
    defaults: dict[str, Any] = {
        "causal_insights": [],
        "risk_assessment": {
            "sla_breach_probability": 0.0,
            "cascading_failure_probability": 0.0,
            "cost_overrun_probability": 0.0,
        },
    }

    if not response:
        return defaults

    json_match = re.search(r"\{[\s\S]*\}", response)
    if json_match:
        try:
            data = json.loads(json_match.group())
            insights = data.get("causal_insights", [])
            risk = data.get("risk_assessment", {})
            return {
                "causal_insights": insights if isinstance(insights, list) else [],
                "risk_assessment": {
                    "sla_breach_probability": float(
                        risk.get("sla_breach_probability", 0.0)
                    ),
                    "cascading_failure_probability": float(
                        risk.get("cascading_failure_probability", 0.0)
                    ),
                    "cost_overrun_probability": float(
                        risk.get("cost_overrun_probability", 0.0)
                    ),
                },
            }
        except (json.JSONDecodeError, ValueError, TypeError):
            pass

    return defaults
