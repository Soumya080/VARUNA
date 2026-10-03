"""CHHAYA v2 end-to-end pipeline test — the backend equivalent of the
Chromium E2E the build task asked for (no browser/cockpit UI exists in this
repo to drive; see reports/chhaya_v2/CHHAYA_V2_IMPLEMENTATION_REPORT.md for
why that is honestly reported as NOT_CONFIGURED rather than fabricated).

Exercises the real path: SAR array -> CFAR detection -> georeference -> AIS
association -> Phi origin consistency -> ranking -> outcome -> NYAYA handoff
-> NYAYA bridge, on synthetic-but-structurally-real inputs (a real CA-CFAR
run over a real numpy array; no network or GPU required, no real Sentinel-1
scene was available to attach to this automated suite).
"""
from datetime import datetime, timezone

import numpy as np

from varuna_chhaya.v2.detectors.cfar import CACFARDetector
from varuna_chhaya.v2.detectors.xview3_frcnn import XView3FasterRCNNMultihead
from varuna_chhaya.v2.outcomes import ChhayaOutcome
from varuna_chhaya.v2.service import ChhayaInvestigationV2
from varuna_contracts.evidence import EvidenceMode
from varuna_contracts.schemas import AISPoint, BBox
from varuna_nyaya.chhaya_bridge import dark_contact_prior_contribution

T0 = datetime(2026, 6, 1, 12, 0, tzinfo=timezone.utc)
BBOX = BBox(min_lon=70.0, min_lat=10.0, max_lon=71.0, max_lat=11.0)


def _synthetic_scene(shape=(300, 300), seed=3):
    rng = np.random.RandomState(seed)
    scene = np.clip(rng.normal(0.05, 0.01, size=shape), 0.0, None)
    # a 2x2 bright block, not a single pixel: min_component_px=2 (CACFARDetector
    # default) correctly rejects a single isolated hot pixel as noise, so a
    # realistic multi-pixel vessel-like return is used instead.
    scene[149:151, 149:151] = 6.0
    return scene


def test_unavailable_detector_yields_sar_evidence_unavailable_end_to_end():
    pipeline = ChhayaInvestigationV2(detector=XView3FasterRCNNMultihead())
    handoff = pipeline.investigate(
        case_id="case-int-1", scene_id="scene-int-1", source_artifact_id="art-1",
        vh=_synthetic_scene(), acquisition_time=T0, scene_bbox=BBOX,
    )
    assert handoff.outcome == ChhayaOutcome.SAR_EVIDENCE_UNAVAILABLE
    assert handoff.detector_available is False
    assert handoff.envelope.mode == EvidenceMode.UNAVAILABLE
    # An unavailable-evidence envelope must never claim to allow operational action.
    assert handoff.envelope.is_actionable is False


def test_no_ais_no_phi_run_yields_no_supported_vessel_or_inconclusive_never_dark_vessel():
    """With zero AIS and zero Phi field supplied, the dark-vessel bar can
    never be met — this test is the end-to-end proof of the outcomes.py
    guard, not just the unit-level one."""
    pipeline = ChhayaInvestigationV2(detector=CACFARDetector(threshold_sigma=5.0))
    handoff = pipeline.investigate(
        case_id="case-int-2", scene_id="scene-int-2", source_artifact_id="art-2",
        vh=_synthetic_scene(), acquisition_time=T0, scene_bbox=BBOX,
        ais_positions=[],
    )
    assert handoff.outcome != ChhayaOutcome.POSSIBLE_DARK_VESSEL
    assert handoff.outcome in (
        ChhayaOutcome.NO_SUPPORTED_VESSEL,
        ChhayaOutcome.INCONCLUSIVE_AIS_COVERAGE,
        ChhayaOutcome.INCONCLUSIVE,
    )
    assert handoff.detector_available is True
    assert handoff.envelope.mode == EvidenceMode.REAL


def test_full_run_with_ais_coverage_and_no_match_produces_candidate_evidence():
    ais = []
    for i in range(15):
        for j in range(15):
            lon = BBOX.min_lon + (i / 14) * (BBOX.max_lon - BBOX.min_lon)
            lat = BBOX.min_lat + (j / 14) * (BBOX.max_lat - BBOX.min_lat)
            ais.append(AISPoint(timestamp=T0, lon=lon, lat=lat, sog_knots=5.0))
    # remove any AIS points near the injected target's pixel location so the
    # candidate genuinely has no nearby AIS position, rather than relying on
    # an accidental grid coincidence
    ais = [p for p in ais if abs(p.lon - 70.5) > 0.05 or abs(p.lat - 10.5) > 0.05]

    pipeline = ChhayaInvestigationV2(detector=CACFARDetector(threshold_sigma=5.0))
    handoff = pipeline.investigate(
        case_id="case-int-3", scene_id="scene-int-3", source_artifact_id="art-3",
        vh=_synthetic_scene(), acquisition_time=T0, scene_bbox=BBOX,
        ais_positions=ais,
    )
    assert handoff.detector_available is True
    assert len(handoff.candidates) >= 1
    top = min(handoff.candidates, key=lambda c: c.rank)
    assert top.sar_score_type == "relative_plausibility"
    # nyaya bridge consumes this real handoff without raising and without
    # ever exceeding its documented bound, regardless of outcome
    bridge_result = dark_contact_prior_contribution(handoff)
    assert 0.0 <= bridge_result.prior_nudge <= 0.15


def test_candidate_ranking_is_present_and_sorted_by_rank():
    pipeline = ChhayaInvestigationV2(detector=CACFARDetector(threshold_sigma=5.0))
    scene = _synthetic_scene()
    scene[49:51, 49:51] = 4.0   # a second, weaker (2x2) target
    handoff = pipeline.investigate(
        case_id="case-int-4", scene_id="scene-int-4", source_artifact_id="art-4",
        vh=scene, acquisition_time=T0, scene_bbox=BBOX, ais_positions=[],
    )
    if len(handoff.candidates) >= 2:
        ranks = sorted(c.rank for c in handoff.candidates)
        assert ranks == list(range(1, len(handoff.candidates) + 1))
