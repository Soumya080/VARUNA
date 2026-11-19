"""CHHAYA v2 orchestrator — wires Phases 2-7 together.

`ChhayaInvestigationV2.investigate()` is the single entry point: SAR arrays
in, `ChhayaEvidenceHandoff` out. Every phase is a plain, independently
testable function/module; this class only sequences them and is the one
place allowed to short-circuit on SAR_EVIDENCE_UNAVAILABLE.
"""
from __future__ import annotations

import uuid
from datetime import datetime

import numpy as np

from varuna_chhaya.v2.ais_association import associate_candidate_with_ais
from varuna_chhaya.v2.contracts import ScoreType, VesselCandidate
from varuna_chhaya.v2.detectors.protocol import VesselDetector, VesselDetectorUnavailable
from varuna_chhaya.v2.georeference import SceneGeoTransform, georeference_candidate
from varuna_chhaya.v2.nyaya_handoff import ChhayaEvidenceHandoff, build_handoff
from varuna_chhaya.v2.origin_consistency import evaluate_origin_consistency
from varuna_chhaya.v2.outcomes import classify_outcome
from varuna_chhaya.v2.ranking import rank_candidates
from varuna_chhaya.coverage import compute_ais_coverage
from varuna_contracts.evidence import EvidenceEnvelope, EvidenceMode, Provenance, ValidityState
from varuna_contracts.phi import PhiField
from varuna_contracts.schemas import AISPoint, BBox, VesselTrack


class ChhayaInvestigationV2:
    def __init__(self, detector: VesselDetector):
        self.detector = detector

    def investigate(
        self,
        *,
        case_id: str,
        scene_id: str,
        source_artifact_id: str,
        vh: np.ndarray,
        acquisition_time: datetime,
        scene_bbox: BBox,
        vv: np.ndarray | None = None,
        ais_positions: list[AISPoint] | None = None,
        phi: PhiField | None = None,
        ais_track: VesselTrack | None = None,
        case_reference_time: datetime | None = None,
        parent_envelope: EvidenceEnvelope | None = None,
    ) -> ChhayaEvidenceHandoff:
        ais_positions = ais_positions or []
        detector_available = self.detector.is_available()
        coverage = compute_ais_coverage(ais_positions, scene_bbox) if ais_positions else 0.0

        if not detector_available:
            outcome, reason = classify_outcome(False, 0, 0, [], {})
            envelope = self._build_envelope(
                parent_envelope, case_id, scene_id, mode=EvidenceMode.UNAVAILABLE,
            )
            return build_handoff(
                case_id, scene_id, outcome, reason,
                self.detector.detector_id, self.detector.detector_mode, False,
                None, [], {}, {}, {}, envelope,
            )

        try:
            raw = self.detector.detect(vh, vv)
        except VesselDetectorUnavailable as exc:
            outcome, reason = classify_outcome(False, 0, 0, [], {})
            envelope = self._build_envelope(parent_envelope, case_id, scene_id, mode=EvidenceMode.UNAVAILABLE)
            return build_handoff(
                case_id, scene_id, outcome, f"{reason} ({exc})",
                self.detector.detector_id, self.detector.detector_mode, False,
                None, [], {}, {}, {}, envelope,
            )

        n_rows, n_cols = vh.shape
        transform = SceneGeoTransform(bbox=scene_bbox, n_rows=n_rows, n_cols=n_cols)

        candidates: list[VesselCandidate] = []
        n_valid_geo = 0
        for i, det in enumerate(raw):
            geo = georeference_candidate(det.row, det.col, transform, acquisition_time, case_reference_time)
            candidate_envelope = self._build_envelope(
                parent_envelope, case_id, scene_id, mode=EvidenceMode.REAL,
                notes="georef_method=linear_affine_bbox_approximation",
            )
            cand = VesselCandidate(
                candidate_id=f"chhaya-cand-{scene_id}-{i:04d}-{uuid.uuid4().hex[:6]}",
                case_id=case_id,
                scene_id=scene_id,
                position=geo.position,
                geolocation_valid=geo.valid,
                geolocation_rejection_reason=geo.rejection_reason,
                pixel_row=det.row,
                pixel_col=det.col,
                detector_source=self.detector.detector_id,
                detector_mode=self.detector.detector_mode,
                vessel_score=det.score,
                score_type=ScoreType.RELATIVE_PLAUSIBILITY,
                length_estimate_m=None,  # pixel->meter needs real resolution metadata; not fabricated here
                vessel_class=None,       # CFAR cannot classify — honestly None, not guessed
                source_artifact_id=source_artifact_id,
                acquisition_time=acquisition_time,
                envelope=candidate_envelope,
            )
            candidates.append(cand)
            if geo.valid:
                n_valid_geo += 1

        ais_results = {
            c.candidate_id: associate_candidate_with_ais(c, ais_positions, scene_bbox)
            for c in candidates
        }
        origin_by_id = {
            c.candidate_id: evaluate_origin_consistency(c, phi, ais_track)
            for c in candidates
        }
        ranking_list = rank_candidates(candidates, origin_by_id)
        ranking_by_id = {r.candidate_id: r for r in ranking_list}

        outcome, reason = classify_outcome(
            True, len(candidates), n_valid_geo, list(ais_results.values()), origin_by_id,
        )

        envelope = self._build_envelope(parent_envelope, case_id, scene_id, mode=EvidenceMode.REAL)
        return build_handoff(
            case_id, scene_id, outcome, reason,
            self.detector.detector_id, self.detector.detector_mode, True,
            coverage, candidates, ais_results, origin_by_id, ranking_by_id, envelope,
        )

    def _build_envelope(
        self, parent: EvidenceEnvelope | None, case_id: str, scene_id: str,
        mode: EvidenceMode, notes: str | None = None,
    ) -> EvidenceEnvelope:
        artifact_id = f"chhaya-v2-{scene_id}-{uuid.uuid4().hex[:8]}"
        # CHHAYA is entitled to assert its OWN artifact's validity here (this
        # is not collapsing trust/confidence/validity into one number — it is
        # the same kind of self-assessment validity_gate.py makes about its
        # own output): evidence that is UNAVAILABLE can never be VALID.
        validity = ValidityState.INCONCLUSIVE if mode is EvidenceMode.UNAVAILABLE else ValidityState.VALID

        if parent is not None:
            return parent.derive(
                artifact_id=artifact_id, produced_by="chhaya_v2",
                model_version=self.detector.get_model_version(),
                validity=validity,
            )
        return EvidenceEnvelope(
            artifact_id=artifact_id,
            case_id=case_id,
            produced_by="chhaya_v2",
            model_version=self.detector.get_model_version(),
            provenance=Provenance(source_id=f"chhaya_v2.{self.detector.detector_id}", notes=notes),
            mode=mode,
            validity_state=validity,
        )
