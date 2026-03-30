"""Phase 6 -- LEARN: Continuous Learning & Policy Improvement.

Tracks prediction accuracy, simulation fidelity, computes RLHF-style reward
signals, detects model drift, and stores experience tuples for future policy
optimisation.
"""

from __future__ import annotations

import time
from collections import deque
from datetime import datetime
from typing import Any

import numpy as np
from scipy import stats as sp_stats

from models.decision import ExecutionRecord, ExecutionStage, LearningUpdate
from models.prediction import PredictionOutput
from models.state import SystemState
from utils.logger import get_logger
from utils.statistics import compute_trend

logger = get_logger(__name__)

# Minimum number of recent errors required before drift detection kicks in
_MIN_DRIFT_SAMPLES = 10

# Weights for reward signal computation (metric importance)
_REWARD_WEIGHTS: dict[str, float] = {
    "latency_p99": 0.25,
    "error_rate_5xx": 0.25,
    "cpu_usage": 0.10,
    "memory_usage": 0.05,
    "sla_compliance": 0.20,
    "queue_depth": 0.05,
    "connection_pool_utilization": 0.05,
    "cloud_spend_rate_hr": 0.05,
}

# Target values for reward computation (lower-is-better metrics get flipped)
_METRIC_TARGETS: dict[str, tuple[float, str]] = {
    # (target_value, direction): "lower" means lower is better
    "latency_p99": (200.0, "lower"),
    "error_rate_5xx": (0.5, "lower"),
    "cpu_usage": (60.0, "lower"),
    "memory_usage": (65.0, "lower"),
    "sla_compliance": (99.5, "higher"),
    "queue_depth": (10.0, "lower"),
    "connection_pool_utilization": (50.0, "lower"),
    "cloud_spend_rate_hr": (35.0, "lower"),
}

# Maximum size of the experience replay buffer
_MAX_BUFFER_SIZE = 500


class LearnPhase:
    """Tracks model accuracy, simulation fidelity, and computes reward signals."""

    def __init__(self, state_history: deque, decision_history: deque):
        """Initialise the learn phase.

        Parameters
        ----------
        state_history:
            Bounded deque of past :class:`SystemState` objects.
        decision_history:
            Bounded deque of past :class:`ExecutionRecord` objects.
        """
        self._state_history = state_history
        self._decision_history = decision_history

        self.prediction_errors: list[dict[str, float]] = []
        self.simulation_fidelity_scores: list[float] = []
        self.reward_buffer: list[dict[str, Any]] = []

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    async def execute(
        self,
        cycle_id: str,
        state: SystemState,
        prediction: PredictionOutput | None,
        execution: ExecutionRecord | None,
    ) -> LearningUpdate:
        """Run the learning update after an action execution cycle."""
        logger.info("learn.start", cycle_id=cycle_id)
        start = time.monotonic()

        pred_errors: dict[str, float] = {}
        sim_fidelity: float | None = None
        reward: float | None = None
        prev_action_accuracy: float | None = None
        drift_detected = False
        policy_update_pending = False
        human_overrides = 0

        # 1. Compare predictions vs actual state
        if prediction is not None and len(self._state_history) >= 2:
            pred_errors = self._compute_prediction_error(prediction, state)
            self.prediction_errors.append(pred_errors)
            # Keep bounded
            if len(self.prediction_errors) > _MAX_BUFFER_SIZE:
                self.prediction_errors = self.prediction_errors[-_MAX_BUFFER_SIZE:]

        # 2. Compare simulated outcome vs actual outcome
        if execution is not None and execution.actual_post_state is not None:
            sim_fidelity = self._compute_simulation_fidelity(
                execution.expected_post_state,
                execution.actual_post_state,
            )
            self.simulation_fidelity_scores.append(sim_fidelity)
            if len(self.simulation_fidelity_scores) > _MAX_BUFFER_SIZE:
                self.simulation_fidelity_scores = self.simulation_fidelity_scores[-_MAX_BUFFER_SIZE:]
        elif execution is not None:
            # No actual_post_state yet; compute fidelity from pre-state vs expected
            # and current state as proxy for actual post-state
            current_dict = self._state_to_dict(state)
            if execution.expected_post_state:
                sim_fidelity = self._compute_simulation_fidelity(
                    execution.expected_post_state,
                    current_dict,
                )
                self.simulation_fidelity_scores.append(sim_fidelity)

        # 3. Compute reward signal for executed action
        if execution is not None and execution.pre_state_snapshot:
            post_dict = self._state_to_dict(state)
            reward = self._compute_reward(
                execution.pre_state_snapshot,
                post_dict,
                execution.action,
            )

            # Store experience tuple
            experience = {
                "cycle_id": cycle_id,
                "pre_state": dict(execution.pre_state_snapshot),
                "action_id": execution.action.id,
                "action_type": execution.action.type.value,
                "reward": reward,
                "post_state": post_dict,
                "timestamp": datetime.utcnow().isoformat(),
            }
            self.reward_buffer.append(experience)
            if len(self.reward_buffer) > _MAX_BUFFER_SIZE:
                self.reward_buffer = self.reward_buffer[-_MAX_BUFFER_SIZE:]

        # 4. Compute previous action accuracy
        if execution is not None and execution.expected_post_state:
            actual = self._state_to_dict(state)
            prev_action_accuracy = self._compute_action_accuracy(
                execution.expected_post_state,
                actual,
            )

        # 5. Detect model drift
        drift_detected = self._detect_model_drift()

        # 6. Count human overrides from decision history
        human_overrides = self._count_recent_overrides()

        # 7. Determine if policy update is needed
        policy_update_pending = (
            drift_detected
            or (len(self.reward_buffer) >= 20 and self._recent_reward_declining())
            or human_overrides > 3
        )

        # 8. Generate recommendations
        recommendations = self._generate_recommendations(
            pred_errors, sim_fidelity, reward, drift_detected, human_overrides
        )

        elapsed = time.monotonic() - start
        logger.info(
            "learn.complete",
            cycle_id=cycle_id,
            reward=round(reward, 4) if reward is not None else None,
            drift=drift_detected,
            n_experiences=len(self.reward_buffer),
            elapsed_ms=round(elapsed * 1000, 1),
        )

        return LearningUpdate(
            cycle_id=cycle_id,
            timestamp=datetime.utcnow(),
            previous_action_accuracy=round(prev_action_accuracy, 4) if prev_action_accuracy is not None else None,
            prediction_errors=pred_errors,
            simulation_fidelity=round(sim_fidelity, 4) if sim_fidelity is not None else None,
            model_drift_detected=drift_detected,
            policy_update_pending=policy_update_pending,
            reward_signal=round(reward, 4) if reward is not None else None,
            human_overrides=human_overrides,
        )

    # ------------------------------------------------------------------
    # Prediction error computation
    # ------------------------------------------------------------------

    def _compute_prediction_error(
        self,
        predicted: Any,
        actual: SystemState,
    ) -> dict[str, float]:
        """Compare predicted q50 metrics vs actual values (MAE).

        ``predicted`` may be a PredictionOutput object or a serialised dict.
        """
        actual_dict = self._state_to_dict(actual)
        errors: dict[str, float] = {}

        # Handle both PredictionOutput objects and serialized dicts
        if isinstance(predicted, dict):
            horizons = predicted.get("horizons", [])
        elif hasattr(predicted, "horizons"):
            horizons = predicted.horizons
        else:
            return errors

        if not horizons:
            return errors

        # Use the shortest-horizon forecast
        if isinstance(horizons[0], dict):
            shortest = min(horizons, key=lambda h: h.get("horizon_seconds", 9999))
            forecasts = shortest.get("metric_forecasts", {})
        else:
            shortest = min(horizons, key=lambda h: h.horizon_seconds)
            forecasts = shortest.metric_forecasts

        for metric_name, qf in forecasts.items():
            if metric_name in actual_dict:
                actual_val = actual_dict[metric_name]
                predicted_val = qf["q50"] if isinstance(qf, dict) else qf.q50
                denominator = max(abs(actual_val), abs(predicted_val), 1e-6)
                nae = abs(actual_val - predicted_val) / denominator
                errors[metric_name] = round(nae, 6)

        return errors

    # ------------------------------------------------------------------
    # Simulation fidelity
    # ------------------------------------------------------------------

    @staticmethod
    def _compute_simulation_fidelity(
        simulated: dict[str, Any],
        actual: dict[str, Any],
    ) -> float:
        """Pearson correlation between simulated and actual metric values.

        Returns a value in [-1, 1] where 1 means perfect fidelity.
        """
        common_keys = sorted(set(simulated.keys()) & set(actual.keys()))
        if len(common_keys) < 3:
            return 0.0

        sim_vals: list[float] = []
        act_vals: list[float] = []
        for k in common_keys:
            try:
                sv = float(simulated[k])
                av = float(actual[k])
                sim_vals.append(sv)
                act_vals.append(av)
            except (TypeError, ValueError):
                continue

        if len(sim_vals) < 3:
            return 0.0

        sim_arr = np.array(sim_vals, dtype=np.float64)
        act_arr = np.array(act_vals, dtype=np.float64)

        # Handle constant arrays
        if np.std(sim_arr) < 1e-10 or np.std(act_arr) < 1e-10:
            # If both are nearly constant and close, fidelity is high
            if np.allclose(sim_arr, act_arr, rtol=0.1, atol=1.0):
                return 0.9
            return 0.0

        corr, _ = sp_stats.pearsonr(sim_arr, act_arr)
        return float(np.nan_to_num(corr, nan=0.0))

    # ------------------------------------------------------------------
    # Reward signal
    # ------------------------------------------------------------------

    @staticmethod
    def _compute_reward(
        pre_state: dict[str, Any],
        post_state: dict[str, Any],
        action: Any,
    ) -> float:
        """Compute an RLHF-style reward signal for the executed action.

        reward = sum of (metric_improvement / target_gap) * weight
        Positive for improvements, negative for degradation.
        """
        total_reward = 0.0
        total_weight = 0.0

        for metric, (target, direction) in _METRIC_TARGETS.items():
            weight = _REWARD_WEIGHTS.get(metric, 0.0)
            if weight == 0.0:
                continue

            try:
                pre_val = float(pre_state.get(metric, target))
                post_val = float(post_state.get(metric, target))
            except (TypeError, ValueError):
                continue

            gap = abs(pre_val - target)
            if gap < 1e-6:
                gap = max(abs(target) * 0.01, 1e-3)

            if direction == "lower":
                # Improvement means post < pre (closer to target)
                improvement = pre_val - post_val
            else:
                # Improvement means post > pre (closer to target)
                improvement = post_val - pre_val

            normalised = improvement / gap
            # Clip to prevent extreme values
            normalised = max(-2.0, min(2.0, normalised))
            total_reward += weight * normalised
            total_weight += weight

        if total_weight > 0:
            total_reward /= total_weight

        return total_reward

    # ------------------------------------------------------------------
    # Action accuracy
    # ------------------------------------------------------------------

    @staticmethod
    def _compute_action_accuracy(
        expected: dict[str, Any],
        actual: dict[str, Any],
    ) -> float:
        """Compute how well the actual outcome matched the expected one.

        Returns a score in [0, 1] where 1 = perfect match.
        """
        common = sorted(set(expected.keys()) & set(actual.keys()))
        if not common:
            return 0.5  # no data to compare

        errors: list[float] = []
        for k in common:
            try:
                ev = float(expected[k])
                av = float(actual[k])
                denom = max(abs(ev), abs(av), 1e-6)
                errors.append(abs(ev - av) / denom)
            except (TypeError, ValueError):
                continue

        if not errors:
            return 0.5

        mean_error = float(np.mean(errors))
        # Convert normalised error to accuracy score [0, 1]
        return max(0.0, min(1.0, 1.0 - mean_error))

    # ------------------------------------------------------------------
    # Model drift detection
    # ------------------------------------------------------------------

    def _detect_model_drift(self) -> bool:
        """Check if prediction errors are systematically increasing.

        Uses a linear trend test on the mean prediction error over recent cycles.
        """
        if len(self.prediction_errors) < _MIN_DRIFT_SAMPLES:
            return False

        # Compute mean error per cycle
        recent = self.prediction_errors[-_MIN_DRIFT_SAMPLES:]
        mean_errors = [
            float(np.mean(list(e.values()))) if e else 0.0
            for e in recent
        ]

        # Check for positive trend (increasing errors)
        slope = compute_trend(mean_errors)
        if slope <= 0:
            return False

        # Statistical significance: simple t-test on slope being > 0
        x = np.arange(len(mean_errors), dtype=np.float64)
        y = np.array(mean_errors, dtype=np.float64)
        if np.std(y) < 1e-10:
            return False

        result = sp_stats.linregress(x, y)
        # Check if slope is significantly positive (p < 0.1)
        return result.slope > 0 and result.pvalue < 0.1

    # ------------------------------------------------------------------
    # Human override tracking
    # ------------------------------------------------------------------

    def _count_recent_overrides(self) -> int:
        """Count how many recent executions were rolled back (proxy for human override)."""
        count = 0
        for record in self._decision_history:
            if hasattr(record, "rolled_back") and record.rolled_back:
                count += 1
            elif hasattr(record, "stage") and record.stage == ExecutionStage.ROLLED_BACK:
                count += 1
        return count

    # ------------------------------------------------------------------
    # Reward trend analysis
    # ------------------------------------------------------------------

    def _recent_reward_declining(self) -> bool:
        """Check if recent rewards show a declining trend."""
        if len(self.reward_buffer) < 10:
            return False
        recent = self.reward_buffer[-10:]
        rewards = [r.get("reward", 0) for r in recent if "reward" in r]
        if len(rewards) < 5:
            return False
        slope = compute_trend(rewards)
        return slope < -0.01

    # ------------------------------------------------------------------
    # Recommendations
    # ------------------------------------------------------------------

    @staticmethod
    def _generate_recommendations(
        pred_errors: dict[str, float],
        sim_fidelity: float | None,
        reward: float | None,
        drift_detected: bool,
        human_overrides: int,
    ) -> list[str]:
        """Generate actionable recommendations from learning signals."""
        recs: list[str] = []

        if drift_detected:
            recs.append(
                "Model drift detected: prediction errors are trending upward. "
                "Consider retraining the forecasting ensemble or increasing "
                "the exponential smoothing alpha."
            )

        if sim_fidelity is not None and sim_fidelity < 0.5:
            recs.append(
                f"Simulation fidelity is low ({sim_fidelity:.2f}). "
                f"The SDE model parameters (theta, sigma) may need recalibration "
                f"against recent operational data."
            )

        if reward is not None and reward < -0.5:
            recs.append(
                f"Negative reward signal ({reward:.2f}) indicates the last action "
                f"degraded system health. Review the action selection logic and "
                f"consider tightening safety constraints."
            )

        if human_overrides > 3:
            recs.append(
                f"High number of human overrides ({human_overrides}). "
                f"The autonomy thresholds may be too aggressive; consider "
                f"increasing CONFIDENCE_THRESHOLD_HIGH."
            )

        # Per-metric prediction error warnings
        high_error_metrics = [
            (name, err)
            for name, err in pred_errors.items()
            if err > 0.3
        ]
        if high_error_metrics:
            names = ", ".join(f"{n} ({e:.0%})" for n, e in high_error_metrics[:3])
            recs.append(
                f"High prediction error on: {names}. "
                f"These metrics may have regime changes not captured by the "
                f"exponential smoothing model."
            )

        if not recs:
            recs.append("All learning signals within normal bounds. No policy updates recommended.")

        return recs

    # ------------------------------------------------------------------
    # Public accessors
    # ------------------------------------------------------------------

    def get_experience_buffer(self) -> list[dict[str, Any]]:
        """Return stored (state, action, reward, next_state) tuples for replay."""
        return list(self.reward_buffer)

    def get_prediction_error_history(self) -> list[dict[str, float]]:
        """Return full prediction error history for analysis."""
        return list(self.prediction_errors)

    def get_simulation_fidelity_history(self) -> list[float]:
        """Return simulation fidelity score history."""
        return list(self.simulation_fidelity_scores)

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _state_to_dict(state: SystemState) -> dict[str, float]:
        out: dict[str, float] = {}
        for vec in (state.infrastructure, state.application, state.business, state.network, state.cost):
            for m in vec.metrics:
                out[m.name] = m.value
        return out
