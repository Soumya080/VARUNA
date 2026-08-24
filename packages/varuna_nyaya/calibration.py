"""
VARUNA GRID — Calibration stub.
"""
from varuna_contracts.evidence import CalibrationState

class CalibrationStub:
    """Calibration is blocked (threat N-06). Returns UNCALIBRATED."""
    def calibrate(self, raw_posteriors: dict) -> dict:
        return raw_posteriors  # identity — no calibration applied

    @property
    def state(self) -> CalibrationState:
        return CalibrationState.UNCALIBRATED
