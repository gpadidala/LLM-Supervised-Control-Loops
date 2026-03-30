"""SCL-Governor control loop phases.

Exports the six phases of the Supervised Control Loop:
    Observe -> Predict -> Simulate -> Decide -> Actuate -> Learn
"""

from phases.observe import ObservePhase
from phases.predict import PredictPhase
from phases.simulate import SimulatePhase
from phases.decide import DecidePhase
from phases.actuate import ActuatePhase
from phases.learn import LearnPhase

__all__ = [
    "ObservePhase",
    "PredictPhase",
    "SimulatePhase",
    "DecidePhase",
    "ActuatePhase",
    "LearnPhase",
]
