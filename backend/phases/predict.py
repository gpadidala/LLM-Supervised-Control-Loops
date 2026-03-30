"""Phase 2 -- PREDICT: Predictive State Modelling.

Predicts system state evolution over planning horizons using an ensemble of
exponential smoothing, linear extrapolation, and (optionally) LLM causal
reasoning.  Outputs multi-horizon probabilistic forecasts and a composite
risk assessment.
"""

from __future__ import annotations

import math
import time
from collections import deque
from datetime import datetime
from typing import Any

import numpy as np

from config import get_settings
from models.prediction import (
    HorizonForecast,
    PredictionOutput,
    QuantileForecast,
    RiskAssessment,
)
from models.state import SystemState
from utils.logger import get_logger
from utils.statistics import compute_quantiles, compute_trend

logger = get_logger(__name__)

# Horizon labels keyed by seconds
_HORIZON_LABELS: dict[int, str] = {300: "5min", 900: "15min", 3600: "1hr"}


class PredictPhase:
    """Predicts system state evolution over planning horizons using ensemble models."""

    def __init__(self, state_history: deque, llm_provider: Any = None):
        """Initialise the predict phase.

        Parameters
        ----------
        state_history:
            Bounded deque of past :class:`SystemState` objects.
        llm_provider:
            Optional LLM with ``async reason(prompt: str) -> str`` method.
        """
        self._history = state_history
        self._llm = llm_provider
        self._settings = get_settings()

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    async def execute(self, state: SystemState, cycle_id: str) -> PredictionOutput:
        """Run prediction across all configured horizons."""
        logger.info("predict.start", cycle_id=cycle_id)
        start = time.monotonic()

        horizons = self._settings.PREDICTION_HORIZONS
        all_metrics = self._collect_all_metrics(state)
        metric_names = [m.name for m in all_metrics]

        # Build historical series per metric
        history_series = self._build_history_series(metric_names, state)

        # 1. Statistical forecasting per horizon
        horizon_forecasts: list[HorizonForecast] = []
        for h in horizons:
            metric_fcs: dict[str, QuantileForecast] = {}
            for name in metric_names:
                series = history_series.get(name, [])
                qf = self._statistical_forecast(series, h)
                metric_fcs[name] = qf
            label = _HORIZON_LABELS.get(h, f"{h}s")
            horizon_forecasts.append(HorizonForecast(
                horizon_seconds=h,
                horizon_label=label,
                metric_forecasts=metric_fcs,
            ))

        # 2. Risk assessment
        risk = self._compute_risk_assessment(state, horizon_forecasts)

        # 3. Causal insights (LLM or rule-based)
        insights = await self._llm_causal_analysis(state, horizon_forecasts)

        # 4. Ensemble confidence
        confidence = self._compute_ensemble_confidence(history_series, horizon_forecasts)

        # 5. Per-metric confidence scores
        confidence_scores: dict[str, float] = {}
        for name in metric_names:
            series = history_series.get(name, [])
            if len(series) >= 10:
                volatility = float(np.std(series[-10:]))
                mean_val = float(np.mean(series[-10:])) if np.mean(series[-10:]) != 0 else 1.0
                cv = volatility / abs(mean_val) if mean_val != 0 else 1.0
                confidence_scores[name] = round(max(0.1, min(1.0, 1.0 - cv)), 3)
            else:
                confidence_scores[name] = 0.3

        elapsed = time.monotonic() - start
        logger.info(
            "predict.complete",
            cycle_id=cycle_id,
            n_horizons=len(horizon_forecasts),
            overall_risk=round(risk.sla_breach_probability, 3),
            elapsed_ms=round(elapsed * 1000, 1),
        )

        return PredictionOutput(
            timestamp=datetime.utcnow(),
            cycle_id=cycle_id,
            horizons=horizon_forecasts,
            risk_assessment=risk,
            causal_insights=insights,
            confidence_scores=confidence_scores,
            model_contributions={"ewma": 0.5, "linear_extrapolation": 0.3, "volatility_band": 0.2},
        )

    # ------------------------------------------------------------------
    # Statistical forecasting
    # ------------------------------------------------------------------

    def _statistical_forecast(self, series: list[float], horizon_seconds: int) -> QuantileForecast:
        """Produce a quantile forecast for a single metric at a single horizon.

        Uses exponentially weighted moving average for q50, and historical
        volatility for prediction intervals (q10 / q90).
        """
        if len(series) < 3:
            # Not enough data -- return current value with wide bands
            val = series[-1] if series else 0.0
            spread = max(abs(val) * 0.2, 1.0)
            return QuantileForecast(q10=val - spread, q50=val, q90=val + spread)

        arr = np.asarray(series, dtype=np.float64)

        # EWMA (alpha decays so recent observations dominate)
        alpha = 0.3
        ewma = arr[0]
        for v in arr[1:]:
            ewma = alpha * v + (1 - alpha) * ewma

        # Linear trend extrapolation
        window = min(30, len(series))
        sl = series[-window:]
        slope = compute_trend(sl, list(range(len(sl))))
        # Number of future steps (assuming 15-second cycles)
        n_steps = horizon_seconds / 15.0
        trend_component = slope * n_steps

        q50 = ewma + trend_component

        # Historical volatility for prediction interval
        if len(arr) >= 5:
            recent = arr[-min(20, len(arr)):]
            volatility = float(np.std(recent, ddof=1))
        else:
            volatility = float(np.std(arr, ddof=0))

        # Widen interval with horizon (sqrt of time scaling)
        horizon_factor = math.sqrt(n_steps)
        spread = 1.645 * volatility * horizon_factor  # ~90% interval for normal

        q10 = q50 - spread
        q90 = q50 + spread

        return QuantileForecast(
            q10=round(q10, 4),
            q50=round(q50, 4),
            q90=round(q90, 4),
        )

    # ------------------------------------------------------------------
    # Risk assessment
    # ------------------------------------------------------------------

    def _compute_risk_assessment(
        self,
        state: SystemState,
        forecasts: list[HorizonForecast],
    ) -> RiskAssessment:
        """Derive SLA breach, cascade, and cost overrun probabilities."""
        all_m = {m.name: m.value for m in self._collect_all_metrics(state)}

        # ---- SLA breach probability ----
        # Based on predicted p99 latency vs SLO threshold (500ms default)
        slo_threshold = 500.0
        sla_probs: list[float] = []
        for hf in forecasts:
            p99_fc = hf.metric_forecasts.get("latency_p99")
            if p99_fc:
                # Probability mass above threshold approximated by normal CDF
                q50 = p99_fc.q50
                sigma = max((p99_fc.q90 - p99_fc.q10) / (2 * 1.645), 1e-6)
                z = (slo_threshold - q50) / sigma
                breach_prob = 1.0 - self._normal_cdf(z)
                sla_probs.append(breach_prob)
        sla_breach = max(sla_probs) if sla_probs else 0.0

        # ---- Cascade probability ----
        # Based on correlation of degrading signals
        err_5xx = all_m.get("error_rate_5xx", 0)
        conn_pool = all_m.get("connection_pool_utilization", 0)
        queue = all_m.get("queue_depth", 0)
        circuit = all_m.get("circuit_breaker_open_pct", 0)

        cascade_signals = 0
        if err_5xx > 2:
            cascade_signals += 1
        if conn_pool > 80:
            cascade_signals += 1
        if queue > 50:
            cascade_signals += 1
        if circuit > 10:
            cascade_signals += 1
        cascade_prob = min(1.0, cascade_signals * 0.25)

        # ---- Cost overrun probability ----
        spend_rate = all_m.get("cloud_spend_rate_hr", 0)
        reserved_util = all_m.get("reserved_utilization_pct", 100)
        cost_overrun = 0.0
        if spend_rate > 50:
            cost_overrun += 0.3
        if reserved_util < 60:
            cost_overrun += 0.2
        cost_overrun = min(1.0, cost_overrun)

        return RiskAssessment(
            sla_breach_probability=round(sla_breach, 4),
            cascading_failure_probability=round(cascade_prob, 4),
            cost_overrun_probability=round(cost_overrun, 4),
        )

    # ------------------------------------------------------------------
    # LLM causal analysis (with rule-based fallback)
    # ------------------------------------------------------------------

    async def _llm_causal_analysis(
        self,
        state: SystemState,
        forecasts: list[HorizonForecast],
    ) -> list[str]:
        """Ask LLM for causal insights, or fall back to rules."""
        if self._llm is None:
            return self._rule_based_insights(state)

        try:
            prompt = self._build_llm_prompt(state, forecasts)
            response = await self._llm.reason(prompt)
            return self._parse_insights(response)
        except Exception as exc:
            logger.warning("predict.llm_unavailable", error=str(exc))
            return self._rule_based_insights(state)

    def _build_llm_prompt(self, state: SystemState, forecasts: list[HorizonForecast]) -> str:
        """Construct a structured prompt for causal analysis."""
        all_m = {m.name: m.value for m in self._collect_all_metrics(state)}

        # Summarise current state
        state_lines = [f"  {k}: {v:.2f}" for k, v in sorted(all_m.items())]

        # Summarise predictions at the shortest horizon
        pred_lines: list[str] = []
        if forecasts:
            hf = forecasts[0]
            for name, qf in hf.metric_forecasts.items():
                pred_lines.append(f"  {name}: q10={qf.q10:.2f} q50={qf.q50:.2f} q90={qf.q90:.2f}")

        # Anomalies
        anom_lines = [
            f"  {a.metric_name} (MAD={a.mad_score:.2f})"
            for a in state.derived.anomaly_scores
            if a.is_anomalous
        ]

        prompt = (
            "You are an SRE observability expert. Analyse the following system telemetry "
            "and predictions.  Identify the top 3-5 causal chains that explain the current "
            "state and could lead to incidents.  Return each insight as a single line.\n\n"
            f"System regime: {state.regime}\n\n"
            "Current metrics:\n" + "\n".join(state_lines) + "\n\n"
            "Anomalous metrics:\n" + ("\n".join(anom_lines) if anom_lines else "  None") + "\n\n"
            + (f"{forecasts[0].horizon_label} forecast:\n" + "\n".join(pred_lines) + "\n\n"
               if forecasts else "") +
            "Provide your analysis as a numbered list of causal insights:"
        )
        return prompt

    @staticmethod
    def _parse_insights(response: str) -> list[str]:
        """Parse LLM response into individual insight strings."""
        insights: list[str] = []
        for line in response.strip().split("\n"):
            line = line.strip()
            if not line:
                continue
            # Strip numbering like "1.", "1)", "- "
            for prefix in ("1.", "2.", "3.", "4.", "5.", "6.", "7.", "8.", "9.",
                           "1)", "2)", "3)", "4)", "5)", "- ", "* "):
                if line.startswith(prefix):
                    line = line[len(prefix):].strip()
                    break
            if line:
                insights.append(line)
        return insights[:5]

    def _rule_based_insights(self, state: SystemState) -> list[str]:
        """Generate insights from deterministic rules when LLM is unavailable."""
        all_m = {m.name: m.value for m in self._collect_all_metrics(state)}
        insights: list[str] = []

        conn_pool = all_m.get("connection_pool_utilization", 0)
        p99 = all_m.get("latency_p99", 0)
        cpu = all_m.get("cpu_usage", 0)
        err_5xx = all_m.get("error_rate_5xx", 0)
        queue = all_m.get("queue_depth", 0)
        mem = all_m.get("memory_usage", 0)
        sla = all_m.get("sla_compliance", 100)
        circuit = all_m.get("circuit_breaker_open_pct", 0)

        # Check trends for rising patterns
        rising_latency = False
        rising_errors = False
        for tv in state.derived.trend_vectors:
            if tv.metric_name == "latency_p99" and tv.delta_5min > 0:
                rising_latency = True
            if tv.metric_name == "error_rate_5xx" and tv.delta_5min > 0:
                rising_errors = True

        if conn_pool > 80 and rising_latency:
            insights.append(
                f"Connection pool saturation ({conn_pool:.0f}%) is driving latency increase; "
                f"p99 at {p99:.0f}ms and rising."
            )

        if cpu > 85 and rising_errors:
            insights.append(
                f"CPU pressure ({cpu:.0f}%) causing request failures; "
                f"5xx error rate at {err_5xx:.1f}% and climbing."
            )

        if queue > 40:
            insights.append(
                f"Queue backpressure building (depth={queue:.0f}); "
                f"consumer throughput may be insufficient."
            )

        if mem > 85:
            insights.append(
                f"Memory utilisation at {mem:.0f}%; risk of OOM kills increasing. "
                f"Consider vertical scaling or memory leak investigation."
            )

        if circuit > 5:
            insights.append(
                f"Circuit breakers {circuit:.0f}% open; inter-service communication degraded. "
                f"Downstream dependency may be failing."
            )

        if sla < 98 and rising_latency:
            insights.append(
                f"SLA compliance at {sla:.1f}%; latency trend suggests further degradation "
                f"within the next prediction horizon."
            )

        if not insights:
            insights.append("System operating within normal parameters; no actionable causal chains detected.")

        return insights[:5]

    # ------------------------------------------------------------------
    # Ensemble confidence
    # ------------------------------------------------------------------

    def _compute_ensemble_confidence(
        self,
        history_series: dict[str, list[float]],
        forecasts: list[HorizonForecast],
    ) -> float:
        """Compute overall confidence in the prediction ensemble.

        Higher history length and lower volatility increase confidence.
        """
        if not history_series:
            return 0.3

        lengths = [len(v) for v in history_series.values()]
        avg_len = np.mean(lengths)
        # Confidence from data availability (saturates around 100 samples)
        data_conf = min(1.0, avg_len / 100)

        # Confidence from prediction interval width (average across metrics)
        widths: list[float] = []
        for hf in forecasts:
            for name, qf in hf.metric_forecasts.items():
                denom = abs(qf.q50) if abs(qf.q50) > 1e-6 else 1.0
                relative_width = (qf.q90 - qf.q10) / denom
                widths.append(relative_width)
        avg_width = float(np.mean(widths)) if widths else 1.0
        width_conf = max(0.1, 1.0 - min(avg_width, 2.0) / 2.0)

        return round(0.6 * data_conf + 0.4 * width_conf, 3)

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def _build_history_series(
        self,
        metric_names: list[str],
        current_state: SystemState,
    ) -> dict[str, list[float]]:
        """Build per-metric time series from history + current state."""
        series: dict[str, list[float]] = {n: [] for n in metric_names}

        for past in self._history:
            past_m = {m.name: m.value for m in self._collect_all_metrics(past)}
            for n in metric_names:
                if n in past_m:
                    series[n].append(past_m[n])

        current_m = {m.name: m.value for m in self._collect_all_metrics(current_state)}
        for n in metric_names:
            if n in current_m:
                series[n].append(current_m[n])

        return series

    @staticmethod
    def _collect_all_metrics(state: SystemState):
        """Gather metrics from all signal-class vectors."""
        out = []
        for vec in (state.infrastructure, state.application, state.business, state.network, state.cost):
            out.extend(vec.metrics)
        return out

    @staticmethod
    def _normal_cdf(z: float) -> float:
        """Standard normal CDF approximation using the error function."""
        return 0.5 * (1.0 + math.erf(z / math.sqrt(2.0)))
