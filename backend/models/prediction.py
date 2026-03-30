"""Pydantic models for the SCL-Governor prediction phase.

Prediction produces multi-horizon probabilistic forecasts, risk assessments,
and causal insights that feed into the simulation phase.
"""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel


class QuantileForecast(BaseModel):
    """Fan-chart quantile triple for a single metric at one horizon."""

    q10: float
    q50: float
    q90: float


class HorizonForecast(BaseModel):
    """Forecasts for every tracked metric at a single time horizon."""

    horizon_seconds: int
    horizon_label: str  # "5min", "15min", "1hr"
    metric_forecasts: dict[str, QuantileForecast]


class RiskAssessment(BaseModel):
    """Aggregate risk probabilities derived from prediction output."""

    sla_breach_probability: float = 0.0
    cascading_failure_probability: float = 0.0
    cost_overrun_probability: float = 0.0


class PredictionOutput(BaseModel):
    """Complete output of the Predict phase for one control cycle."""

    timestamp: datetime
    cycle_id: str
    horizons: list[HorizonForecast]
    risk_assessment: RiskAssessment
    causal_insights: list[str] = []
    confidence_scores: dict[str, float] = {}
    model_contributions: dict[str, float] = {}
