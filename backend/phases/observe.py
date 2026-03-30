"""Phase 1 -- OBSERVE: Telemetry Ingestion & State Construction.

Ingests live telemetry from Prometheus (or synthetic fallback) and constructs
the unified system state tensor S(t) including derived analytics such as
trend vectors, anomaly scores, correlation matrices, and FFT seasonality.
"""

from __future__ import annotations

import asyncio
import time
from collections import deque
from datetime import datetime
from typing import Any

import numpy as np

from config import get_settings
from models.state import (
    AnomalyScore,
    DerivedMetrics,
    MetricValue,
    StateSummary,
    SystemState,
    TelemetryVector,
    TrendVector,
)
from utils.anomaly import compute_mad_score, compute_z_score, detect_anomalies, granger_causality_test
from utils.logger import get_logger
from utils.statistics import compute_correlation_matrix, compute_trend, fft_seasonality

logger = get_logger(__name__)


class ObservePhase:
    """Ingests live telemetry and constructs unified system state tensor S(t)."""

    # PromQL query templates for each signal class
    _INFRA_QUERIES: dict[str, str] = {
        "cpu_usage": 'avg(rate(container_cpu_usage_seconds_total{namespace!="kube-system"}[5m])) * 100',
        "memory_usage": "avg(container_memory_usage_bytes / container_spec_memory_limit_bytes) * 100",
        "disk_iops": 'sum(rate(node_disk_reads_completed_total[5m]) + rate(node_disk_writes_completed_total[5m]))',
        "network_throughput_mbps": "sum(rate(node_network_receive_bytes_total[5m]) + rate(node_network_transmit_bytes_total[5m])) / 1048576",
        "pod_count": "count(kube_pod_status_phase{phase='Running'})",
        "node_health": "avg(up{job='node-exporter'})",
    }

    _APP_QUERIES: dict[str, str] = {
        "request_rate": "sum(rate(http_requests_total[5m]))",
        "latency_p50": 'histogram_quantile(0.50, sum(rate(http_request_duration_seconds_bucket[5m])) by (le)) * 1000',
        "latency_p95": 'histogram_quantile(0.95, sum(rate(http_request_duration_seconds_bucket[5m])) by (le)) * 1000',
        "latency_p99": 'histogram_quantile(0.99, sum(rate(http_request_duration_seconds_bucket[5m])) by (le)) * 1000',
        "error_rate_4xx": 'sum(rate(http_requests_total{status=~"4.."}[5m])) / sum(rate(http_requests_total[5m])) * 100',
        "error_rate_5xx": 'sum(rate(http_requests_total{status=~"5.."}[5m])) / sum(rate(http_requests_total[5m])) * 100',
        "queue_depth": "sum(rabbitmq_queue_messages_ready) or vector(0)",
        "connection_pool_utilization": "avg(hikaricp_connections_active / hikaricp_connections_max) * 100",
    }

    _BUSINESS_QUERIES: dict[str, str] = {
        "active_users": "sum(active_user_sessions_total)",
        "transaction_throughput": "sum(rate(business_transactions_total[5m]))",
        "sla_compliance": "avg(sla_compliance_ratio) * 100",
    }

    _NETWORK_QUERIES: dict[str, str] = {
        "inter_service_latency_ms": "avg(istio_request_duration_milliseconds_sum / istio_request_duration_milliseconds_count)",
        "dns_resolution_time_ms": "avg(dns_lookup_duration_seconds) * 1000",
        "tcp_retransmits": "sum(rate(node_netstat_Tcp_RetransSegs[5m]))",
        "circuit_breaker_open_pct": "avg(envoy_circuit_breakers_default_cx_open) * 100",
    }

    _COST_QUERIES: dict[str, str] = {
        "cloud_spend_rate_hr": "sum(cloud_cost_per_hour)",
        "reserved_utilization_pct": "avg(reserved_instance_utilization) * 100",
        "spot_instance_count": "count(kube_node_labels{label_lifecycle='spot'})",
    }

    def __init__(self, prometheus_connector: Any, state_history: deque):
        """Initialise the observe phase.

        Parameters
        ----------
        prometheus_connector:
            Object with an ``async query(promql: str) -> list[dict]`` method.
            Can be ``None`` for demo/synthetic mode.
        state_history:
            Bounded deque of past :class:`SystemState` snapshots used for
            trend and anomaly computation.
        """
        self._prom = prometheus_connector
        self._history = state_history
        self._settings = get_settings()
        self._rng = np.random.default_rng(seed=42)
        self._synthetic_t: float = 0.0  # virtual clock for synthetic patterns

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    async def execute(self, cycle_id: str) -> SystemState:
        """Run the full observe phase and return the assembled SystemState."""
        logger.info("observe.start", cycle_id=cycle_id)
        start = time.monotonic()

        # 1. Fetch telemetry from all signal classes in parallel
        infra, app, biz, net, cost = await asyncio.gather(
            self._fetch_infrastructure_metrics(),
            self._fetch_application_metrics(),
            self._fetch_business_metrics(),
            self._fetch_network_metrics(),
            self._fetch_cost_metrics(),
        )

        now = datetime.utcnow()

        # 2. Build raw SystemState (derived filled in next step)
        state = SystemState(
            timestamp=now,
            cycle_id=cycle_id,
            infrastructure=infra,
            application=app,
            business=biz,
            network=net,
            cost=cost,
            derived=DerivedMetrics(trend_vectors=[], anomaly_scores=[]),
        )

        # 3. Compute derived metrics from history
        state.derived = self._compute_derived_metrics(state, self._history)

        # 4. Determine regime from anomalies and key metrics
        state.regime = self._classify_regime(state)

        elapsed = time.monotonic() - start
        logger.info(
            "observe.complete",
            cycle_id=cycle_id,
            regime=state.regime,
            n_anomalies=sum(1 for a in state.derived.anomaly_scores if a.is_anomalous),
            elapsed_ms=round(elapsed * 1000, 1),
        )
        return state

    # ------------------------------------------------------------------
    # Telemetry fetchers (per signal class)
    # ------------------------------------------------------------------

    async def _fetch_infrastructure_metrics(self) -> TelemetryVector:
        metrics = await self._query_or_synthesise(
            self._INFRA_QUERIES,
            synthetic_fn=self._synthetic_infra,
        )
        return TelemetryVector(signal_class="infrastructure", metrics=metrics, source="prometheus")

    async def _fetch_application_metrics(self) -> TelemetryVector:
        metrics = await self._query_or_synthesise(
            self._APP_QUERIES,
            synthetic_fn=self._synthetic_app,
        )
        return TelemetryVector(signal_class="application", metrics=metrics, source="prometheus")

    async def _fetch_business_metrics(self) -> TelemetryVector:
        metrics = await self._query_or_synthesise(
            self._BUSINESS_QUERIES,
            synthetic_fn=self._synthetic_business,
        )
        return TelemetryVector(signal_class="business", metrics=metrics, source="prometheus")

    async def _fetch_network_metrics(self) -> TelemetryVector:
        metrics = await self._query_or_synthesise(
            self._NETWORK_QUERIES,
            synthetic_fn=self._synthetic_network,
        )
        return TelemetryVector(signal_class="network", metrics=metrics, source="prometheus")

    async def _fetch_cost_metrics(self) -> TelemetryVector:
        metrics = await self._query_or_synthesise(
            self._COST_QUERIES,
            synthetic_fn=self._synthetic_cost,
        )
        return TelemetryVector(signal_class="cost", metrics=metrics, source="prometheus")

    # ------------------------------------------------------------------
    # Prometheus helper with synthetic fallback
    # ------------------------------------------------------------------

    async def _query_or_synthesise(
        self,
        queries: dict[str, str],
        synthetic_fn: Any,
    ) -> list[MetricValue]:
        """Try Prometheus first; fall back to synthetic data on failure."""
        now = datetime.utcnow()
        if self._prom is not None:
            try:
                results: list[MetricValue] = []
                for name, promql in queries.items():
                    raw = await self._prom.query(promql)
                    value = self._extract_scalar(raw)
                    results.append(MetricValue(name=name, value=value, timestamp=now))
                return results
            except Exception as exc:
                logger.warning("observe.prometheus_unavailable", error=str(exc))

        # Synthetic / demo mode
        return synthetic_fn(now)

    @staticmethod
    def _extract_scalar(prom_result: list[dict]) -> float:
        """Extract a single float from a Prometheus instant-query result."""
        if prom_result and isinstance(prom_result, list):
            first = prom_result[0]
            if "value" in first:
                return float(first["value"][1])
        return 0.0

    # ------------------------------------------------------------------
    # Synthetic data generators (realistic ranges + seasonality)
    # ------------------------------------------------------------------

    def _base_seasonal(self, period: float = 3600.0, amplitude: float = 1.0) -> float:
        """Sinusoidal component based on virtual clock."""
        return amplitude * float(np.sin(2.0 * np.pi * self._synthetic_t / period))

    def _tick_clock(self, dt: float = 15.0) -> None:
        self._synthetic_t += dt

    def _synthetic_infra(self, now: datetime) -> list[MetricValue]:
        self._tick_clock()
        s = self._base_seasonal(period=3600, amplitude=10)
        return [
            MetricValue(name="cpu_usage", value=float(np.clip(45 + s + self._rng.normal(0, 5), 0, 100)), timestamp=now, unit="%"),
            MetricValue(name="memory_usage", value=float(np.clip(55 + s * 0.5 + self._rng.normal(0, 3), 0, 100)), timestamp=now, unit="%"),
            MetricValue(name="disk_iops", value=float(max(0, 1200 + s * 80 + self._rng.normal(0, 100))), timestamp=now, unit="iops"),
            MetricValue(name="network_throughput_mbps", value=float(max(0, 450 + s * 30 + self._rng.normal(0, 40))), timestamp=now, unit="Mbps"),
            MetricValue(name="pod_count", value=float(max(1, int(24 + self._rng.integers(-2, 3)))), timestamp=now, unit="pods"),
            MetricValue(name="node_health", value=float(np.clip(1.0 + self._rng.normal(0, 0.02), 0, 1)), timestamp=now, unit="ratio"),
        ]

    def _synthetic_app(self, now: datetime) -> list[MetricValue]:
        s = self._base_seasonal(period=1800, amplitude=1)
        base_rps = 850 + s * 100
        # Correlated: higher request rate -> higher latency
        lat_factor = max(1.0, base_rps / 800)
        return [
            MetricValue(name="request_rate", value=float(max(0, base_rps + self._rng.normal(0, 50))), timestamp=now, unit="req/s"),
            MetricValue(name="latency_p50", value=float(max(1, 45 * lat_factor + self._rng.normal(0, 5))), timestamp=now, unit="ms"),
            MetricValue(name="latency_p95", value=float(max(1, 120 * lat_factor + self._rng.normal(0, 15))), timestamp=now, unit="ms"),
            MetricValue(name="latency_p99", value=float(max(1, 280 * lat_factor + self._rng.normal(0, 30))), timestamp=now, unit="ms"),
            MetricValue(name="error_rate_4xx", value=float(np.clip(1.2 + self._rng.exponential(0.3), 0, 15)), timestamp=now, unit="%"),
            MetricValue(name="error_rate_5xx", value=float(np.clip(0.3 + self._rng.exponential(0.1), 0, 10)), timestamp=now, unit="%"),
            MetricValue(name="queue_depth", value=float(max(0, 15 + s * 8 + self._rng.normal(0, 5))), timestamp=now, unit="msgs"),
            MetricValue(name="connection_pool_utilization", value=float(np.clip(60 + s * 10 + self._rng.normal(0, 8), 0, 100)), timestamp=now, unit="%"),
        ]

    def _synthetic_business(self, now: datetime) -> list[MetricValue]:
        s = self._base_seasonal(period=7200, amplitude=1)
        return [
            MetricValue(name="active_users", value=float(max(0, 1200 + s * 300 + self._rng.normal(0, 80))), timestamp=now, unit="users"),
            MetricValue(name="transaction_throughput", value=float(max(0, 340 + s * 60 + self._rng.normal(0, 25))), timestamp=now, unit="tx/s"),
            MetricValue(name="sla_compliance", value=float(np.clip(99.2 + self._rng.normal(0, 0.3), 90, 100)), timestamp=now, unit="%"),
        ]

    def _synthetic_network(self, now: datetime) -> list[MetricValue]:
        s = self._base_seasonal(period=2400, amplitude=1)
        return [
            MetricValue(name="inter_service_latency_ms", value=float(max(0.5, 8 + s * 2 + self._rng.normal(0, 1.5))), timestamp=now, unit="ms"),
            MetricValue(name="dns_resolution_time_ms", value=float(max(0.1, 2.5 + self._rng.exponential(0.5))), timestamp=now, unit="ms"),
            MetricValue(name="tcp_retransmits", value=float(max(0, 12 + s * 3 + self._rng.normal(0, 4))), timestamp=now, unit="pkt/s"),
            MetricValue(name="circuit_breaker_open_pct", value=float(np.clip(self._rng.exponential(1.5), 0, 100)), timestamp=now, unit="%"),
        ]

    def _synthetic_cost(self, now: datetime) -> list[MetricValue]:
        return [
            MetricValue(name="cloud_spend_rate_hr", value=float(max(0, 42.5 + self._rng.normal(0, 3))), timestamp=now, unit="$/hr"),
            MetricValue(name="reserved_utilization_pct", value=float(np.clip(72 + self._rng.normal(0, 5), 0, 100)), timestamp=now, unit="%"),
            MetricValue(name="spot_instance_count", value=float(max(0, int(6 + self._rng.integers(-1, 2)))), timestamp=now, unit="instances"),
        ]

    # ------------------------------------------------------------------
    # Derived metrics computation
    # ------------------------------------------------------------------

    def _compute_derived_metrics(self, state: SystemState, history: deque) -> DerivedMetrics:
        """Compute trends, anomalies, correlations, and seasonality."""
        all_metrics = self._collect_all_metrics(state)
        metric_names = [m.name for m in all_metrics]
        metric_values = {m.name: m.value for m in all_metrics}

        # Build per-metric historical series
        history_series: dict[str, list[float]] = {name: [] for name in metric_names}
        for past_state in history:
            past_metrics = self._collect_all_metrics(past_state)
            past_lookup = {m.name: m.value for m in past_metrics}
            for name in metric_names:
                if name in past_lookup:
                    history_series[name].append(past_lookup[name])

        # Append current values
        for name in metric_names:
            history_series[name].append(metric_values[name])

        # Trend vectors
        trends = self._compute_trends(metric_names, history_series)

        # Anomaly scores
        anomaly_scores = self._run_anomaly_detection(all_metrics, history_series)

        # Correlation matrix (only if enough history)
        corr_matrix: dict[str, dict[str, float]] = {}
        series_for_corr = {k: v for k, v in history_series.items() if len(v) >= 5}
        if len(series_for_corr) >= 2:
            corr_matrix = compute_correlation_matrix(series_for_corr)

        # FFT seasonality
        seasonality_phase: dict[str, float] = {}
        for name, series in history_series.items():
            if len(series) >= 16:
                periods = fft_seasonality(series, top_k=1)
                if periods:
                    seasonality_phase[name] = periods[0]

        return DerivedMetrics(
            trend_vectors=trends,
            anomaly_scores=anomaly_scores,
            correlation_matrix=corr_matrix,
            seasonality_phase=seasonality_phase,
        )

    def _compute_trends(
        self,
        metric_names: list[str],
        history_series: dict[str, list[float]],
    ) -> list[TrendVector]:
        """Compute trend deltas over 5m, 15m, and 1h windows."""
        trends: list[TrendVector] = []
        # Approximate sample counts: at 15s cycle, 5m~20, 15m~60, 1hr~240
        windows = {"delta_5min": 20, "delta_15min": 60, "delta_1hr": 240}

        for name in metric_names:
            series = history_series.get(name, [])
            if len(series) < 2:
                trends.append(TrendVector(metric_name=name))
                continue

            def _trend_over_window(s: list[float], w: int) -> float:
                sl = s[-w:]
                ts = list(range(len(sl)))
                return compute_trend(sl, ts)

            d5 = _trend_over_window(series, min(windows["delta_5min"], len(series)))
            d15 = _trend_over_window(series, min(windows["delta_15min"], len(series)))
            d1h = _trend_over_window(series, min(windows["delta_1hr"], len(series)))

            trends.append(TrendVector(
                metric_name=name,
                delta_5min=round(d5, 6),
                delta_15min=round(d15, 6),
                delta_1hr=round(d1h, 6),
            ))
        return trends

    def _run_anomaly_detection(
        self,
        metrics: list[MetricValue],
        history_series: dict[str, list[float]],
    ) -> list[AnomalyScore]:
        """Compute MAD-based anomaly scores and simplified Granger causality."""
        scores: list[AnomalyScore] = []
        anomalous_names: list[str] = []

        for m in metrics:
            series = history_series.get(m.name, [])
            if len(series) < 5:
                scores.append(AnomalyScore(
                    metric_name=m.name,
                    z_score=0.0,
                    mad_score=0.0,
                    is_anomalous=False,
                ))
                continue

            z_vals = compute_z_score(series)
            mad_vals = compute_mad_score(series)
            # Use the score for the latest (current) value
            z_current = z_vals[-1] if z_vals else 0.0
            mad_current = mad_vals[-1] if mad_vals else 0.0
            is_anom = abs(mad_current) > 3.0

            scores.append(AnomalyScore(
                metric_name=m.name,
                z_score=round(z_current, 4),
                mad_score=round(mad_current, 4),
                is_anomalous=is_anom,
            ))
            if is_anom:
                anomalous_names.append(m.name)

        # Run simplified Granger causality between anomalous metrics
        if len(anomalous_names) >= 2:
            for i, name_a in enumerate(anomalous_names):
                series_a = history_series.get(name_a, [])
                causal_links: list[str] = []
                for name_b in anomalous_names:
                    if name_a == name_b:
                        continue
                    series_b = history_series.get(name_b, [])
                    if len(series_a) < 10 or len(series_b) < 10:
                        continue
                    min_len = min(len(series_a), len(series_b))
                    try:
                        result = granger_causality_test(
                            series_b[-min_len:],
                            series_a[-min_len:],
                            max_lag=min(5, min_len // 3),
                        )
                        if result["significant"]:
                            causal_links.append(name_b)
                    except (ValueError, np.linalg.LinAlgError):
                        pass

                # Update the corresponding AnomalyScore
                for sc in scores:
                    if sc.metric_name == name_a:
                        sc.causal_attribution = causal_links
                        break

        return scores

    # ------------------------------------------------------------------
    # Regime classification
    # ------------------------------------------------------------------

    def _classify_regime(self, state: SystemState) -> str:
        """Classify the current operating regime based on key indicators."""
        n_anomalies = sum(1 for a in state.derived.anomaly_scores if a.is_anomalous)
        all_m = {m.name: m.value for m in self._collect_all_metrics(state)}

        cpu = all_m.get("cpu_usage", 0)
        err_5xx = all_m.get("error_rate_5xx", 0)
        sla = all_m.get("sla_compliance", 100)
        p99 = all_m.get("latency_p99", 0)

        # Critical: multiple strong signals of failure
        if (err_5xx > 5 or sla < 95 or cpu > 90) and n_anomalies >= 3:
            return "critical"
        if n_anomalies >= 2 or cpu > 80 or err_5xx > 2 or p99 > 1000:
            return "degraded"
        return "normal"

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _collect_all_metrics(state: SystemState) -> list[MetricValue]:
        """Gather metrics from all five signal-class vectors."""
        out: list[MetricValue] = []
        for vec in (state.infrastructure, state.application, state.business, state.network, state.cost):
            out.extend(vec.metrics)
        return out
