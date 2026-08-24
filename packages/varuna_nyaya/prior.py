"""
VARUNA GRID — Behavioural emission prior calculation.
"""
from varuna_contracts.schemas import VesselTrack
from varuna_contracts.phi import PhiField
from varuna_contracts.decision import PriorContribution

TYPE_WEIGHTS = {
    "tanker": 1.5,
    "cargo": 1.2,
    "fishing": 0.8,
    "unknown": 1.0
}

def compute_speed_anomaly(track: VesselTrack) -> float:
    return 0.1 # mock for M2

def compute_loiter_score(track: VesselTrack, phi: PhiField) -> float:
    return 0.1 # mock for M2

def compute_night_proximity(track: VesselTrack, phi: PhiField) -> float:
    return 0.1 # mock for M2

def compute_prior(track: VesselTrack, phi: PhiField) -> PriorContribution:
    gap_score = min(1.0, track.total_gap_minutes / (24 * 60)) 
    speed_anomaly = compute_speed_anomaly(track)
    loiter_score = compute_loiter_score(track, phi)
    night_proximity = compute_night_proximity(track, phi)
    
    # Safe default if vessel_type is an Enum or string
    v_type = getattr(track.vessel_type, 'value', str(track.vessel_type)).lower() if track.vessel_type else "unknown"
    type_weight = TYPE_WEIGHTS.get(v_type, 1.0)

    combined = (
        1.0
        + 0.3 * gap_score
        + 0.2 * speed_anomaly
        + 0.2 * loiter_score
        + 0.1 * night_proximity
    ) * type_weight

    return PriorContribution(
        gap_score=gap_score,
        speed_anomaly=speed_anomaly,
        loiter_score=loiter_score,
        night_proximity=night_proximity,
        type_weight=type_weight,
        combined=combined,
        weights_version="hand_tuned_v1",
    )
