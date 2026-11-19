from typing import Any
from varuna_contracts.evidence import TrustState
from varuna_data_eng.schemas.quality import QualityState, QualityVerdict
from varuna_data_eng.pipeline.quality_engine import QualityEngine
from varuna_data_eng.schemas.canonical_sar import CanonicalSAR
from varuna_data_eng.schemas.oil_mask import OilMask
from varuna_data_eng.schemas.ais import RawAISTrack
from varuna_data_eng.schemas.forcing import ForcingCube

class DataGuardV2:
    """Wraps QualityEngine to bridge engineering verdicts to the locked TrustState."""
    
    def __init__(self, synthetic_mode: bool = False):
        self.synthetic_mode = synthetic_mode
        self.engine = QualityEngine(synthetic_mode=synthetic_mode)

    def evaluate(self, artifact: Any) -> TrustState:
        if isinstance(artifact, CanonicalSAR):
            state = self.engine.validate_sar(artifact)
        elif isinstance(artifact, OilMask):
            state = self.engine.validate_mask(artifact)
        elif isinstance(artifact, RawAISTrack):
            state = self.engine.validate_ais(artifact)
        elif isinstance(artifact, ForcingCube):
            state = self.engine.validate_forcing(artifact)
        else:
            return TrustState.QUARANTINED

        return self._map_to_trust(state)
        
    def _map_to_trust(self, state: QualityState) -> TrustState:
        if state.overall_verdict == QualityVerdict.PASS:
            return TrustState.TRUSTED
        elif state.overall_verdict == QualityVerdict.WARN:
            return TrustState.DEGRADED
        else:
            return TrustState.QUARANTINED
