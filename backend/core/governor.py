"""SCL-Governor: Main control loop orchestrator.

Runs the six-phase Supervised Control Loop at configurable intervals:
    Observe -> Predict -> Simulate -> Decide -> Actuate -> Learn

Each cycle produces a ``ControlCycleOutput`` that is stored in memory and
optionally broadcast to WebSocket clients.
"""

from __future__ import annotations

import asyncio
import traceback
from collections import deque
from datetime import datetime, timezone
from typing import Any

from config import get_settings
from connectors.kubernetes import KubernetesConnector
from connectors.notifications import NotificationConnector
from connectors.prometheus import PrometheusConnector
from core.regime import RegimeDetector
from core.safety import SafetyManager
from llm.provider import LLMProvider
from models.decision import (
    ControlCycleOutput,
    Decision,
    ExecutionRecord,
    LearningUpdate,
)
from models.state import StateSummary, SystemState
from phases.observe import ObservePhase
from phases.predict import PredictPhase
from phases.simulate import SimulatePhase
from phases.decide import DecidePhase
from phases.actuate import ActuatePhase
from phases.learn import LearnPhase
from utils.logger import get_logger

log = get_logger(__name__)


class SCLGovernor:
    """Main control loop orchestrator.

    Runs the 6-phase cycle at configurable intervals, adapting the cycle
    frequency based on the current operating regime (faster during critical
    periods, slower during normal operation).
    """

    def __init__(self) -> None:
        self.settings = get_settings()

        # History buffers
        self.state_history: deque[SystemState] = deque(maxlen=1000)
        self.decision_history: deque[dict[str, Any]] = deque(maxlen=500)
        self.cycle_outputs: deque[ControlCycleOutput] = deque(maxlen=200)

        # Runtime state
        self.current_regime: str = "normal"
        self.is_running: bool = False
        self.cycle_count: int = 0
        self._ws_manager: Any | None = None  # set externally for WebSocket broadcast
        self._loop_task: asyncio.Task | None = None

        # Human override / feedback store
        self.overrides: list[dict[str, Any]] = []

        # --- Connectors ---
        self.prometheus = PrometheusConnector(self.settings.PROMETHEUS_URL)
        self.k8s: KubernetesConnector | None = (
            KubernetesConnector(self.settings)
            if self.settings.KUBERNETES_IN_CLUSTER or self.settings.KUBERNETES_KUBECONFIG
            else None
        )
        self.notifications = NotificationConnector(self.settings)
        self.llm = LLMProvider(self.settings)

        # --- Phases ---
        self.observe = ObservePhase(self.prometheus, self.state_history)
        self.predict = PredictPhase(self.state_history, self.llm)
        self.simulate = SimulatePhase(self.settings)
        self.decide = DecidePhase(self.llm, self.settings)
        self.actuate = ActuatePhase(self.k8s, self.notifications)
        self.learn_phase = LearnPhase(self.state_history, self.decision_history)

        # --- Safety & regime ---
        self.safety = SafetyManager(self.settings)
        self.regime_detector = RegimeDetector()

        log.info("governor_initialized", prometheus_url=self.settings.PROMETHEUS_URL)

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    async def start(self) -> None:
        """Start the control loop running in the background."""
        if self.is_running:
            log.warning("governor_already_running")
            return
        self.is_running = True
        log.info("governor_starting")
        while self.is_running:
            try:
                await self.run_cycle()
            except Exception:
                log.error("governor_cycle_unhandled", exc=traceback.format_exc())
            await asyncio.sleep(self._get_cycle_interval())

    def stop(self) -> None:
        """Signal the control loop to stop after the current cycle."""
        self.is_running = False
        log.info("governor_stopping")

    # ------------------------------------------------------------------
    # Single cycle
    # ------------------------------------------------------------------

    async def run_cycle(self) -> ControlCycleOutput:
        """Execute one complete control cycle through all six phases.

        Returns the composite ``ControlCycleOutput`` for this cycle.
        """
        cycle_id = (
            f"scl-{datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')}"
            f"-{self.cycle_count:04d}"
        )
        self.cycle_count += 1
        start_time = datetime.now(timezone.utc)

        try:
            # Phase 1: OBSERVE
            log.info("cycle.observe.start", cycle_id=cycle_id)
            state = await self.observe.execute(cycle_id)
            state.regime = self.current_regime
            self.state_history.append(state)

            # Update regime
            self.current_regime = self.regime_detector.detect(
                state, self.state_history
            )
            state.regime = self.current_regime

            # Phase 2: PREDICT
            log.info("cycle.predict.start", cycle_id=cycle_id)
            prediction = await self.predict.execute(state, cycle_id)

            # Phase 3: SIMULATE
            log.info("cycle.simulate.start", cycle_id=cycle_id)
            actions = self.safety.generate_safe_actions(state, self.current_regime)
            simulation = await self.simulate.execute(
                state, prediction, actions, cycle_id
            )

            # Phase 4: DECIDE
            log.info("cycle.decide.start", cycle_id=cycle_id)
            decision = await self.decide.execute(
                state, prediction, simulation, cycle_id
            )

            # Phase 5: ACTUATE
            log.info("cycle.actuate.start", cycle_id=cycle_id)
            execution = await self.actuate.execute(decision, state, cycle_id)
            self.decision_history.append(
                {"decision": decision, "execution": execution}
            )

            # Phase 6: LEARN
            log.info("cycle.learn.start", cycle_id=cycle_id)
            prev_prediction = self._get_previous_prediction()
            prev_execution = self._get_previous_execution()
            learning = await self.learn_phase.execute(
                cycle_id, state, prev_prediction, prev_execution
            )

            # Build output
            output = self._build_cycle_output(
                cycle_id=cycle_id,
                state=state,
                prediction=prediction,
                simulation=simulation,
                decision=decision,
                execution=execution,
                learning=learning,
            )
            self.cycle_outputs.append(output)

            elapsed = (datetime.now(timezone.utc) - start_time).total_seconds()
            log.info(
                "cycle.complete",
                cycle_id=cycle_id,
                regime=self.current_regime,
                elapsed_s=round(elapsed, 2),
            )

            # Broadcast via WebSocket
            if self._ws_manager:
                try:
                    await self._ws_manager.broadcast(output.model_dump(mode="json"))
                except Exception:
                    log.warning("ws_broadcast_failed", cycle_id=cycle_id)

            return output

        except Exception as exc:
            log.error(
                "cycle.failed",
                cycle_id=cycle_id,
                error=str(exc),
                traceback=traceback.format_exc(),
            )
            # Return a minimal error output
            now = datetime.now(timezone.utc)
            error_output = ControlCycleOutput(
                cycle_id=cycle_id,
                timestamp=now,
                system_regime=self.current_regime,
                state_summary=StateSummary(
                    top_concerns=[f"Cycle failed: {str(exc)[:200]}"],
                    anomalies_detected=0,
                    regime=self.current_regime,
                ),
                prediction={"status": "error", "error": str(exc)[:200]},
                simulation_results={"status": "error"},
                decision={"status": "error"},
                execution_status="failed",
                learning_update=LearningUpdate(
                    cycle_id=cycle_id,
                    timestamp=now,
                ).model_dump(mode="json"),
            )
            self.cycle_outputs.append(error_output)
            return error_output

    # ------------------------------------------------------------------
    # Cycle interval
    # ------------------------------------------------------------------

    def _get_cycle_interval(self) -> float:
        """Adjust the cycle interval based on the current regime.

        Cycles run faster during critical periods and at the base rate
        during normal operation.
        """
        base = float(self.settings.CONTROL_CYCLE_INTERVAL)
        if self.current_regime == "critical":
            return max(5.0, base / 3.0)
        if self.current_regime == "degraded":
            return max(8.0, base / 2.0)
        if self.current_regime == "recovery":
            return max(10.0, base / 1.5)
        return base

    # ------------------------------------------------------------------
    # History helpers
    # ------------------------------------------------------------------

    def _get_previous_prediction(self) -> Any | None:
        """Return the PredictionOutput from the previous cycle, if any."""
        # The prediction isn't stored directly; look in decision_history
        # For learn phase comparison, we return None if unavailable
        if len(self.cycle_outputs) < 2:
            return None
        prev = self.cycle_outputs[-2]
        return prev.prediction if isinstance(prev.prediction, dict) else None

    def _get_previous_execution(self) -> Any | None:
        """Return the ExecutionRecord from the previous cycle, if any."""
        if len(self.decision_history) < 2:
            return None
        prev = self.decision_history[-2]
        return prev.get("execution")

    # ------------------------------------------------------------------
    # Output builder
    # ------------------------------------------------------------------

    def _build_cycle_output(
        self,
        cycle_id: str,
        state: SystemState,
        prediction: Any,
        simulation: Any,
        decision: Any,
        execution: Any,
        learning: Any,
    ) -> ControlCycleOutput:
        """Assemble the composite output for one control cycle."""
        now = datetime.now(timezone.utc)

        # Build state summary
        anomaly_count = sum(
            1 for a in state.derived.anomaly_scores if a.is_anomalous
        )
        top_concerns: list[str] = []
        for a in state.derived.anomaly_scores:
            if a.is_anomalous:
                top_concerns.append(
                    f"{a.metric_name} anomalous (MAD={a.mad_score:.2f})"
                )
        if not top_concerns:
            top_concerns = ["No anomalies detected"]

        state_summary = StateSummary(
            top_concerns=top_concerns[:5],
            anomalies_detected=anomaly_count,
            regime=self.current_regime,
        )

        # Serialize prediction
        prediction_dict: dict[str, Any]
        if hasattr(prediction, "model_dump"):
            prediction_dict = prediction.model_dump(mode="json")
        elif isinstance(prediction, dict):
            prediction_dict = prediction
        else:
            prediction_dict = {"status": "unknown"}

        # Serialize simulation
        simulation_dict: dict[str, Any]
        if hasattr(simulation, "model_dump"):
            simulation_dict = simulation.model_dump(mode="json")
        elif isinstance(simulation, dict):
            simulation_dict = simulation
        else:
            simulation_dict = {"status": "unknown"}

        # Serialize decision
        decision_dict: dict[str, Any]
        if hasattr(decision, "model_dump"):
            decision_dict = decision.model_dump(mode="json")
        elif isinstance(decision, dict):
            decision_dict = decision
        else:
            decision_dict = {"status": "unknown"}

        # Determine execution status
        if hasattr(execution, "stage"):
            exec_status = execution.stage.value if hasattr(execution.stage, "value") else str(execution.stage)
        elif isinstance(execution, dict):
            exec_status = execution.get("stage", "completed")
        else:
            exec_status = "completed"

        # Serialize learning
        learning_dict: dict[str, Any]
        if hasattr(learning, "model_dump"):
            learning_dict = learning.model_dump(mode="json")
        elif isinstance(learning, dict):
            learning_dict = learning
        else:
            learning_dict = {"cycle_id": cycle_id}

        return ControlCycleOutput(
            cycle_id=cycle_id,
            timestamp=now,
            system_regime=self.current_regime,
            state_summary=state_summary,
            prediction=prediction_dict,
            simulation_results=simulation_dict,
            decision=decision_dict,
            execution_status=exec_status,
            learning_update=learning_dict,
        )

    # ------------------------------------------------------------------
    # Status and query
    # ------------------------------------------------------------------

    def get_status(self) -> dict[str, Any]:
        """Return the current governor status."""
        return {
            "is_running": self.is_running,
            "cycle_count": self.cycle_count,
            "current_regime": self.current_regime,
            "state_history_size": len(self.state_history),
            "decision_history_size": len(self.decision_history),
            "cycle_outputs_size": len(self.cycle_outputs),
            "llm_available": self.llm.is_available,
            "k8s_available": self.k8s is not None,
            "cycle_interval_seconds": self._get_cycle_interval(),
        }

    def get_recent_cycles(self, n: int = 20) -> list[ControlCycleOutput]:
        """Return the last *n* cycle outputs, newest first."""
        return list(reversed(list(self.cycle_outputs)[-n:]))

    def get_cycle_by_id(self, cycle_id: str) -> ControlCycleOutput | None:
        """Look up a specific cycle output by its ID."""
        for output in reversed(self.cycle_outputs):
            if output.cycle_id == cycle_id:
                return output
        return None
