"""Regime detection for the SCL-Governor control loop.

Detects the current operating regime of the managed system based on
telemetry, SLO compliance, and recent trend history.
"""

from __future__ import annotations

from collections import deque
from typing import Any

from models.state import SystemState
from utils.logger import get_logger

log = get_logger(__name__)

# ---------------------------------------------------------------------------
# Regime constants
# ---------------------------------------------------------------------------
REGIME_NORMAL = "normal"
REGIME_DEGRADED = "degraded"
REGIME_CRITICAL = "critical"
REGIME_RECOVERY = "recovery"
REGIME_MAINTENANCE = "maintenance"

# Threshold defaults
_ERROR_RATE_CRITICAL = 5.0      # percent
_ERROR_RATE_DEGRADED = 1.0      # percent
_LATENCY_P99_SLO = 500.0       # ms
_LATENCY_P99_DEGRADED_FRAC = 0.80  # 80% of SLO -> degraded
_RESOURCE_DEGRADED_PCT = 90.0   # CPU or memory > 90%
_RECOVERY_IMPROVEMENT_CYCLES = 3


class RegimeDetector:
    """Detects system operating regime: normal, degraded, critical, recovery, maintenance.

    Rules (evaluated in priority order):
    - **maintenance**: maintenance window flag or annotation present
    - **critical**: any SLO breached, error rate > 5%, or multiple services degraded
    - **degraded**: p99 latency > 80% of SLO, error rate > 1%, or resource > 90%
    - **recovery**: was critical/degraded, now improving for 3+ cycles
    - **normal**: everything within bounds
    """

    def __init__(self) -> None:
        self._previous_regime: str = REGIME_NORMAL
        self._improving_streak: int = 0

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def detect(self, state: SystemState, history: deque) -> str:
        """Determine the current regime from *state* and recent *history*."""
        metrics = self._extract_key_metrics(state)

        # Check maintenance first
        if metrics.get("maintenance_window", False):
            regime = REGIME_MAINTENANCE
        elif self._is_critical(metrics):
            regime = REGIME_CRITICAL
            self._improving_streak = 0
        elif self._is_degraded(metrics):
            regime = REGIME_DEGRADED
            self._improving_streak = 0
        elif self._previous_regime in (REGIME_CRITICAL, REGIME_DEGRADED):
            # Check if we are recovering
            if self._is_improving(history, n_cycles=_RECOVERY_IMPROVEMENT_CYCLES):
                self._improving_streak += 1
                regime = REGIME_RECOVERY
            else:
                # Still in the prior regime
                regime = self._previous_regime
                self._improving_streak = 0
        elif self._previous_regime == REGIME_RECOVERY:
            if self._is_improving(history, n_cycles=_RECOVERY_IMPROVEMENT_CYCLES):
                self._improving_streak += 1
                # After sustained recovery, promote to normal
                if self._improving_streak >= _RECOVERY_IMPROVEMENT_CYCLES * 2:
                    regime = REGIME_NORMAL
                    self._improving_streak = 0
                else:
                    regime = REGIME_RECOVERY
            else:
                regime = REGIME_NORMAL
                self._improving_streak = 0
        else:
            regime = REGIME_NORMAL
            self._improving_streak = 0

        if regime != self._previous_regime:
            log.info(
                "regime_change",
                old=self._previous_regime,
                new=regime,
                cycle_id=state.cycle_id,
            )
        self._previous_regime = regime
        return regime

    # ------------------------------------------------------------------
    # Metric extraction
    # ------------------------------------------------------------------

    def _extract_key_metrics(self, state: SystemState) -> dict[str, Any]:
        """Extract key metrics from the state for regime classification."""
        out: dict[str, Any] = {
            "error_rate_5xx": 0.0,
            "error_rate_4xx": 0.0,
            "latency_p99": 0.0,
            "cpu_usage": 0.0,
            "memory_usage": 0.0,
            "sla_compliance": 100.0,
            "maintenance_window": False,
        }

        # Walk all telemetry vectors
        for vec in (
            state.infrastructure,
            state.application,
            state.business,
            state.network,
            state.cost,
        ):
            for m in vec.metrics:
                name_lower = m.name.lower()
                if "error_rate_5xx" in name_lower or "error_rate_5" in name_lower:
                    out["error_rate_5xx"] = max(out["error_rate_5xx"], m.value)
                elif "error_rate_4xx" in name_lower or "error_rate_4" in name_lower:
                    out["error_rate_4xx"] = max(out["error_rate_4xx"], m.value)
                elif "latency_p99" in name_lower:
                    out["latency_p99"] = max(out["latency_p99"], m.value)
                elif "cpu_usage" in name_lower or "cpu_util" in name_lower:
                    out["cpu_usage"] = max(out["cpu_usage"], m.value)
                elif "memory_usage" in name_lower or "mem_usage" in name_lower:
                    out["memory_usage"] = max(out["memory_usage"], m.value)
                elif "sla_compliance" in name_lower:
                    out["sla_compliance"] = min(out["sla_compliance"], m.value)
                elif "maintenance" in name_lower:
                    out["maintenance_window"] = m.value > 0

        return out

    # ------------------------------------------------------------------
    # Regime classification helpers
    # ------------------------------------------------------------------

    def _is_critical(self, m: dict[str, Any]) -> bool:
        """True when the system is in a critical state."""
        # SLO breach: p99 latency exceeds SLO
        if m["latency_p99"] > _LATENCY_P99_SLO:
            return True
        # High 5xx error rate
        if m["error_rate_5xx"] > _ERROR_RATE_CRITICAL:
            return True
        # Multiple degradation signals simultaneously
        degradation_signals = 0
        if m["cpu_usage"] > _RESOURCE_DEGRADED_PCT:
            degradation_signals += 1
        if m["memory_usage"] > _RESOURCE_DEGRADED_PCT:
            degradation_signals += 1
        if m["error_rate_5xx"] > _ERROR_RATE_DEGRADED:
            degradation_signals += 1
        if m["latency_p99"] > _LATENCY_P99_SLO * _LATENCY_P99_DEGRADED_FRAC:
            degradation_signals += 1
        if degradation_signals >= 3:
            return True
        # SLA below 99% is a breach
        if m["sla_compliance"] < 99.0:
            return True
        return False

    def _is_degraded(self, m: dict[str, Any]) -> bool:
        """True when the system is degraded but not critical."""
        if m["latency_p99"] > _LATENCY_P99_SLO * _LATENCY_P99_DEGRADED_FRAC:
            return True
        if m["error_rate_5xx"] > _ERROR_RATE_DEGRADED:
            return True
        if m["cpu_usage"] > _RESOURCE_DEGRADED_PCT:
            return True
        if m["memory_usage"] > _RESOURCE_DEGRADED_PCT:
            return True
        return False

    # ------------------------------------------------------------------
    # Improvement detection
    # ------------------------------------------------------------------

    def _is_improving(self, history: deque, n_cycles: int = 3) -> bool:
        """Check if key metrics are improving over the last *n_cycles*.

        'Improving' means the error rate and latency are trending downward
        (or at least not increasing) across the last *n* states.
        """
        if len(history) < n_cycles:
            return False

        recent = list(history)[-n_cycles:]
        error_rates: list[float] = []
        latencies: list[float] = []

        for st in recent:
            m = self._extract_key_metrics(st)
            error_rates.append(m["error_rate_5xx"])
            latencies.append(m["latency_p99"])

        # Check monotonic non-increase (each value <= previous)
        error_improving = all(
            error_rates[i] <= error_rates[i - 1] + 0.01
            for i in range(1, len(error_rates))
        )
        latency_improving = all(
            latencies[i] <= latencies[i - 1] + 1.0
            for i in range(1, len(latencies))
        )

        return error_improving and latency_improving
