"""Statistical utilities used across SCL-Governor phases.

All public functions accept plain Python types and return plain Python types
to stay decoupled from the Pydantic model layer.
"""

from __future__ import annotations

import numpy as np
from numpy.fft import fft, fftfreq


# ---------------------------------------------------------------------------
# Correlation matrix (Pearson)
# ---------------------------------------------------------------------------

def compute_correlation_matrix(
    metrics: dict[str, list[float]],
) -> dict[str, dict[str, float]]:
    """Compute the pairwise Pearson correlation matrix for named metric series.

    Parameters
    ----------
    metrics:
        Mapping of metric name to a list of observed values.  All lists must
        have the same length.

    Returns
    -------
    A nested dict ``result[metric_a][metric_b] = r`` for every pair.
    """
    names = list(metrics.keys())
    if not names:
        return {}

    matrix = np.column_stack([np.asarray(metrics[n], dtype=np.float64) for n in names])
    corr = np.corrcoef(matrix, rowvar=False)

    # corrcoef can return a scalar if there is only one metric
    if corr.ndim == 0:
        return {names[0]: {names[0]: 1.0}}

    result: dict[str, dict[str, float]] = {}
    for i, name_a in enumerate(names):
        row: dict[str, float] = {}
        for j, name_b in enumerate(names):
            val = float(corr[i, j])
            # Replace NaN (e.g. constant series) with 0.0
            row[name_b] = val if np.isfinite(val) else 0.0
        result[name_a] = row
    return result


# ---------------------------------------------------------------------------
# Linear trend (slope via least-squares)
# ---------------------------------------------------------------------------

def compute_trend(values: list[float], timestamps: list[float]) -> float:
    """Return the linear trend slope of *values* over *timestamps*.

    Uses ordinary least-squares (``numpy.polyfit`` degree 1).  If fewer than
    two data points are provided the slope is 0.0.
    """
    if len(values) < 2 or len(timestamps) < 2:
        return 0.0
    coeffs = np.polyfit(
        np.asarray(timestamps, dtype=np.float64),
        np.asarray(values, dtype=np.float64),
        deg=1,
    )
    slope = float(coeffs[0])
    return slope if np.isfinite(slope) else 0.0


# ---------------------------------------------------------------------------
# Quantile computation
# ---------------------------------------------------------------------------

def compute_quantiles(
    values: list[float],
    quantiles: list[float],
) -> dict[str, float]:
    """Compute arbitrary quantiles of *values*.

    Parameters
    ----------
    quantiles:
        List of quantile levels in [0, 1] (e.g. ``[0.10, 0.50, 0.90]``).

    Returns
    -------
    Dict keyed by ``"qXX"`` (e.g. ``"q10"``, ``"q50"``).
    """
    arr = np.asarray(values, dtype=np.float64)
    result: dict[str, float] = {}
    for q in quantiles:
        label = f"q{int(q * 100)}"
        result[label] = float(np.quantile(arr, q))
    return result


# ---------------------------------------------------------------------------
# FFT-based seasonality detection
# ---------------------------------------------------------------------------

def fft_seasonality(
    values: list[float],
    sample_rate: float,
) -> dict[str, float]:
    """Identify the dominant seasonal frequency and phase via FFT.

    Parameters
    ----------
    values:
        Evenly-sampled time-series values.
    sample_rate:
        Samples per second (e.g. 1/15 for one sample every 15 s).

    Returns
    -------
    Dict with:
        - ``dominant_frequency_hz``: frequency of the strongest non-DC component
        - ``dominant_period_seconds``: 1 / dominant_frequency (or inf)
        - ``dominant_phase_radians``: phase angle in radians
        - ``power``: spectral power of the dominant component
    """
    n = len(values)
    if n < 4:
        return {
            "dominant_frequency_hz": 0.0,
            "dominant_period_seconds": float("inf"),
            "dominant_phase_radians": 0.0,
            "power": 0.0,
        }

    arr = np.asarray(values, dtype=np.float64)
    # Remove mean to ignore DC
    arr = arr - np.mean(arr)

    spectrum = fft(arr)
    freqs = fftfreq(n, d=1.0 / sample_rate)

    # Only consider positive frequencies (skip DC at index 0)
    pos_mask = freqs > 0
    pos_freqs = freqs[pos_mask]
    pos_power = np.abs(spectrum[pos_mask]) ** 2

    if len(pos_power) == 0:
        return {
            "dominant_frequency_hz": 0.0,
            "dominant_period_seconds": float("inf"),
            "dominant_phase_radians": 0.0,
            "power": 0.0,
        }

    peak_idx = int(np.argmax(pos_power))
    dominant_freq = float(pos_freqs[peak_idx])
    dominant_phase = float(np.angle(spectrum[pos_mask][peak_idx]))
    dominant_power = float(pos_power[peak_idx])
    period = 1.0 / dominant_freq if dominant_freq > 0 else float("inf")

    return {
        "dominant_frequency_hz": dominant_freq,
        "dominant_period_seconds": period,
        "dominant_phase_radians": dominant_phase,
        "power": dominant_power,
    }


# ---------------------------------------------------------------------------
# Pareto frontier
# ---------------------------------------------------------------------------

def compute_pareto_frontier(
    objectives: list[list[float]],
    minimize: list[bool],
) -> list[int]:
    """Return indices of Pareto-optimal points.

    Parameters
    ----------
    objectives:
        A list of N points, each being a list of M objective values.
    minimize:
        A list of M booleans.  ``True`` means that objective should be
        minimized; ``False`` means maximized.

    Returns
    -------
    Sorted list of indices into *objectives* that are on the Pareto frontier.
    """
    if not objectives:
        return []

    arr = np.asarray(objectives, dtype=np.float64)
    n = arr.shape[0]

    # Flip sign of objectives that should be maximized so we can treat
    # everything as minimization.
    signs = np.array([1.0 if m else -1.0 for m in minimize])
    normed = arr * signs

    is_pareto = np.ones(n, dtype=bool)
    for i in range(n):
        if not is_pareto[i]:
            continue
        for j in range(n):
            if i == j or not is_pareto[j]:
                continue
            # j dominates i if j <= i in all objectives and j < i in at least one
            if np.all(normed[j] <= normed[i]) and np.any(normed[j] < normed[i]):
                is_pareto[i] = False
                break

    return sorted(int(idx) for idx in np.where(is_pareto)[0])


# ---------------------------------------------------------------------------
# CVaR (Conditional Value-at-Risk)
# ---------------------------------------------------------------------------

def compute_cvar(values: list[float], alpha: float = 0.95) -> float:
    """Compute the Conditional Value-at-Risk (CVaR) at confidence *alpha*.

    CVaR (also called Expected Shortfall) is the expected value of the worst
    ``(1 - alpha)`` fraction of outcomes.  Higher values indicate greater
    tail risk.

    Parameters
    ----------
    values:
        Sample of outcomes (e.g. objective function values from Monte Carlo).
    alpha:
        Confidence level in (0, 1).  ``0.95`` means we look at the worst 5 %.

    Returns
    -------
    The CVaR scalar.  If the sample is empty, returns 0.0.
    """
    if not values:
        return 0.0

    arr = np.asarray(values, dtype=np.float64)
    var_threshold = float(np.quantile(arr, alpha))
    tail = arr[arr >= var_threshold]

    if len(tail) == 0:
        return var_threshold

    return float(np.mean(tail))
