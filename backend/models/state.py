"""Pydantic models for the SCL-Governor system state tensor.

These models represent the complete observable state of the managed system
at a single point in time, including raw telemetry, derived analytics, and
a human-readable summary.
"""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, Field


class MetricValue(BaseModel):
    """A single metric observation."""

    name: str
    value: float
    timestamp: datetime
    labels: dict[str, str] = {}
    unit: str = ""


class TelemetryVector(BaseModel):
    """A vector of metrics belonging to one signal class."""

    signal_class: str = Field(
        ...,
        description="One of: infrastructure, application, business, network, cost",
    )
    metrics: list[MetricValue]
    source: str = ""


class TrendVector(BaseModel):
    """Rate-of-change deltas for a single metric across multiple horizons."""

    metric_name: str
    delta_5min: float = 0.0
    delta_15min: float = 0.0
    delta_1hr: float = 0.0


class AnomalyScore(BaseModel):
    """Anomaly scores computed for a single metric."""

    metric_name: str
    z_score: float
    mad_score: float
    is_anomalous: bool = False
    causal_attribution: list[str] = []


class DerivedMetrics(BaseModel):
    """Second-order analytics derived from raw telemetry."""

    trend_vectors: list[TrendVector]
    anomaly_scores: list[AnomalyScore]
    correlation_matrix: dict[str, dict[str, float]] = {}
    seasonality_phase: dict[str, float] = {}


class SystemState(BaseModel):
    """Complete snapshot of the managed system at one control-cycle tick."""

    timestamp: datetime
    cycle_id: str
    infrastructure: TelemetryVector
    application: TelemetryVector
    business: TelemetryVector
    network: TelemetryVector
    cost: TelemetryVector
    derived: DerivedMetrics
    regime: str = "normal"


class StateSummary(BaseModel):
    """Human-readable digest of the current system state."""

    top_concerns: list[str]
    anomalies_detected: int = 0
    sla_breach_eta_minutes: float | None = None
    regime: str = "normal"
