"""Anomaly detection utilities for the SCL-Governor observe phase.

All functions operate on plain Python lists and return plain Python types so
they can be used without tight coupling to any model layer.
"""

from __future__ import annotations

import numpy as np
from scipy import stats as sp_stats


# ---------------------------------------------------------------------------
# Z-score (standard)
# ---------------------------------------------------------------------------

def compute_z_score(values: list[float]) -> list[float]:
    """Compute standard Z-scores for *values*.

    Returns a list of the same length.  If standard deviation is zero every
    Z-score is returned as 0.0.
    """
    arr = np.asarray(values, dtype=np.float64)
    mean = np.mean(arr)
    std = np.std(arr, ddof=0)
    if std == 0.0:
        return [0.0] * len(values)
    return ((arr - mean) / std).tolist()


# ---------------------------------------------------------------------------
# MAD score (Modified Z-score using Median Absolute Deviation)
# ---------------------------------------------------------------------------

_MAD_CONSISTENCY_CONSTANT = 0.6745  # k for normal distribution


def compute_mad_score(values: list[float]) -> list[float]:
    """Compute Modified Z-scores based on the Median Absolute Deviation.

    The Modified Z-score is defined as:
        M_i = 0.6745 * (x_i - median) / MAD

    where MAD = median(|x_i - median|).  If MAD is zero every score is 0.0.
    """
    arr = np.asarray(values, dtype=np.float64)
    median = np.median(arr)
    mad = np.median(np.abs(arr - median))
    if mad == 0.0:
        return [0.0] * len(values)
    return (_MAD_CONSISTENCY_CONSTANT * (arr - median) / mad).tolist()


# ---------------------------------------------------------------------------
# Anomaly detection (MAD-based)
# ---------------------------------------------------------------------------

def detect_anomalies(
    values: list[float],
    threshold: float = 3.0,
) -> list[bool]:
    """Flag anomalies using Modified Z-scores with the given *threshold*.

    Returns a list of booleans the same length as *values*.
    """
    mad_scores = compute_mad_score(values)
    return [abs(s) > threshold for s in mad_scores]


# ---------------------------------------------------------------------------
# Simplified Granger causality test
# ---------------------------------------------------------------------------

def granger_causality_test(
    x: list[float],
    y: list[float],
    max_lag: int = 5,
) -> dict:
    """Run a simplified Granger-causality F-test.

    Tests whether lagged values of *x* improve a linear prediction of *y*
    beyond what lagged values of *y* alone provide.

    Returns a dict with keys:
        - ``f_statistic``: the F-value for the best lag
        - ``p_value``: associated p-value
        - ``best_lag``: the lag that gave the strongest signal
        - ``significant``: bool, True if p < 0.05
        - ``lag_results``: per-lag F and p values

    If the series are too short for the requested *max_lag* the result will
    indicate non-significance with NaN statistics.
    """
    x_arr = np.asarray(x, dtype=np.float64)
    y_arr = np.asarray(y, dtype=np.float64)

    n = len(y_arr)
    if n != len(x_arr):
        raise ValueError("x and y must have the same length")

    lag_results: list[dict] = []
    best_f = -1.0
    best_p = 1.0
    best_lag = 1

    for lag in range(1, max_lag + 1):
        if n - lag < lag + 2:
            # Not enough observations for a meaningful test at this lag.
            lag_results.append({"lag": lag, "f_statistic": float("nan"), "p_value": 1.0})
            continue

        # Build the restricted model matrix (only lagged y)
        y_target = y_arr[lag:]
        restricted_cols = np.column_stack(
            [y_arr[lag - k - 1 : n - k - 1] for k in range(lag)]
        )
        # Add intercept
        restricted_X = np.column_stack([np.ones(len(y_target)), restricted_cols])

        # Build the unrestricted model matrix (lagged y + lagged x)
        unrestricted_cols = np.column_stack(
            [x_arr[lag - k - 1 : n - k - 1] for k in range(lag)]
        )
        unrestricted_X = np.column_stack([restricted_X, unrestricted_cols])

        # OLS via least-squares
        try:
            _, rss_r, _, _ = np.linalg.lstsq(restricted_X, y_target, rcond=None)
            _, rss_u, _, _ = np.linalg.lstsq(unrestricted_X, y_target, rcond=None)
        except np.linalg.LinAlgError:
            lag_results.append({"lag": lag, "f_statistic": float("nan"), "p_value": 1.0})
            continue

        rss_restricted = float(rss_r[0]) if len(rss_r) > 0 else float(np.sum((y_target - restricted_X @ np.linalg.lstsq(restricted_X, y_target, rcond=None)[0]) ** 2))
        rss_unrestricted = float(rss_u[0]) if len(rss_u) > 0 else float(np.sum((y_target - unrestricted_X @ np.linalg.lstsq(unrestricted_X, y_target, rcond=None)[0]) ** 2))

        df_diff = lag  # number of extra parameters
        df_resid = len(y_target) - unrestricted_X.shape[1]

        if df_resid <= 0 or rss_unrestricted <= 0:
            lag_results.append({"lag": lag, "f_statistic": float("nan"), "p_value": 1.0})
            continue

        f_stat = ((rss_restricted - rss_unrestricted) / df_diff) / (rss_unrestricted / df_resid)
        p_val = float(1.0 - sp_stats.f.cdf(f_stat, df_diff, df_resid))

        lag_results.append({"lag": lag, "f_statistic": float(f_stat), "p_value": p_val})

        if f_stat > best_f:
            best_f = f_stat
            best_p = p_val
            best_lag = lag

    return {
        "f_statistic": float(best_f) if best_f >= 0 else float("nan"),
        "p_value": best_p,
        "best_lag": best_lag,
        "significant": best_p < 0.05,
        "lag_results": lag_results,
    }
