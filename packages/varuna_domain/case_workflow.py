"""
VARUNA GRID — Case Workflow Orchestrator.

Executes the end-to-end vertical slice:
CASE -> INGEST -> DATA GUARD -> PRATIVARTAN -> NYAYA -> VALIDITY GATE
                  -> PRAMAN -> EVENT SPINE -> API
"""
import uuid
import time
import numpy as np
from typing import List, Optional
from datetime import datetime, timezone

from varuna_domain.entities import Case, CaseStatus, ScientificStatus, Artifact
from varuna_domain.ports import CaseRepository, ArtifactRepository, EventRepository, ObjectStore
from varuna_praman.praman import PramanService
from varuna_pravaah.event_spine import EventSpine
from varuna_data_guard.guard import evaluate_data_guard, GuardVerdict
from varuna_contracts.schemas import VesselTrack


from varuna_domain.ports import CaseRepository, ArtifactRepository, EventRepository, ObjectStore

class CaseWorkflow:
    """Orchestrates the full CASE-0001 vertical slice."""

    def __init__(self,
                 case_repo: CaseRepository,
                 artifact_repo: ArtifactRepository,
                 event_repo: EventRepository,
                 object_store: Optional[ObjectStore] = None):
        self.cases = case_repo
        self.artifacts = artifact_repo
        self.events_store = event_repo
        self.praman = PramanService(self.artifacts, object_store)
        self.event_spine = EventSpine(self.events_store)

    def create_case(self, case_id: Optional[str] = None) -> Case:
        case_id = case_id or f"CASE-{uuid.uuid4().hex[:8].upper()}"
        case = Case(case_id)
        self.cases.save(case)
        self.event_spine.emit("case.created", case_id, actor="workflow")
        return case

    def ingest(self, case: Case, slick_lons: np.ndarray, slick_lats: np.ndarray,
               tracks: List[VesselTrack], obs_time_hours: float,
               age_prior_mean: float = 36.0, age_prior_std: float = 24.0):
        """Ingest input and run Data Guard."""
        case.transition(CaseStatus.INGESTING, "workflow")

        # Register input artifact
        input_artifact = self.praman.register_artifact(
            artifact_type="input_slick", case_id=case.case_id,
            produced_by="ingest", data={
                "n_slick_points": len(slick_lons),
                "n_tracks": len(tracks),
                "obs_time_hours": obs_time_hours,
            },
        )
        self.event_spine.emit("artifact.created", case.case_id, payload={
            "artifact_id": input_artifact.artifact_id, "type": "input_slick",
        })

        # Data Guard
        case.transition(CaseStatus.GUARDING, "workflow")
        guard_result = evaluate_data_guard(
            slick_lons=slick_lons, slick_lats=slick_lats,
            n_tracks=len(tracks), obs_time_hours=obs_time_hours,
        )
        self.event_spine.emit("slick.detected", case.case_id, payload={
            "guard_verdict": guard_result.verdict.value,
        })

        if guard_result.verdict == GuardVerdict.QUARANTINED:
            case.transition(CaseStatus.QUARANTINED, "data_guard")
            case.error = "; ".join(guard_result.blocking_reasons)
            self.event_spine.emit("case.failed", case.case_id, payload={
                "reason": "quarantined", "details": guard_result.blocking_reasons,
            })
            return case, guard_result

        # Store context for later phases
        case.metadata["input"] = {
            "slick_lons": slick_lons.tolist(), "slick_lats": slick_lats.tolist(),
            "tracks": [t.model_dump() for t in tracks], "obs_time_hours": obs_time_hours,
            "age_prior_mean": age_prior_mean, "age_prior_std": age_prior_std,
        }
        self.cases.save(case)
        return case, guard_result

    def reconstruct(self, case: Case, seed: int = 42) -> dict:
        """Run PRATIVARTAN to produce PhiField."""
        from varuna_nyaya.services import PrativartanService

        case.transition(CaseStatus.RECONSTRUCTING, "workflow")
        inp = case.metadata["input"]
        svc = PrativartanService()
        slick_id = f"slick-{uuid.uuid4().hex[:8]}"

        phi = svc.reconstruct_origin(
            slick_lons=np.array(inp["slick_lons"]), slick_lats=np.array(inp["slick_lats"]),
            obs_time_hours=inp["obs_time_hours"],
            case_id=case.case_id, slick_id=slick_id,
            age_prior_mean_hours=inp["age_prior_mean"],
            age_prior_std_hours=inp["age_prior_std"],
            seed=seed,
        )
        case.metadata["phi"] = phi.model_dump(mode="json")
        self.cases.save(case)

        phi_artifact = self.praman.register_artifact(
            artifact_type="phi_field", case_id=case.case_id,
            produced_by="prativartan", data={"phi_id": phi.phi_id, "data_path": phi.data_path},
        )
        self.event_spine.emit("origin.generated", case.case_id, payload={
            "phi_id": phi.phi_id, "artifact_id": phi_artifact.artifact_id,
        })
        return {"phi_id": phi.phi_id, "artifact_id": phi_artifact.artifact_id}

    def attribute(self, case: Case, latent_prior: float = 0.5) -> dict:
        """Run NYAYA attribution."""
        from varuna_nyaya.services import NyayaService, ValidityService
        from varuna_contracts.phi import PhiField
        from varuna_contracts.schemas import VesselTrack

        case.transition(CaseStatus.ATTRIBUTING, "workflow")
        inp = case.metadata["input"]
        phi = PhiField.model_validate(case.metadata["phi"])
        tracks = [VesselTrack.model_validate(t) for t in inp["tracks"]]
        nyaya = NyayaService()

        attribution = nyaya.attribute(
            phi=phi, tracks=tracks,
            case_id=case.case_id,
            slick_lons=np.array(inp["slick_lons"]), slick_lats=np.array(inp["slick_lats"]),
            latent_prior=latent_prior,
        )
        case.metadata["attribution"] = attribution.model_dump(mode="json")
        self.cases.save(case)

        attr_artifact = self.praman.register_artifact(
            artifact_type="attribution", case_id=case.case_id,
            produced_by="nyaya", data={
                "decision_state": attribution.decision_state.value,
                "n_candidates": len(attribution.candidates),
                "latent_probability": attribution.latent_probability,
            },
        )
        self.event_spine.emit("attribution.generated", case.case_id, payload={
            "decision": attribution.decision_state.value,
            "artifact_id": attr_artifact.artifact_id,
        })

        # Validity Gate
        case.transition(CaseStatus.EVALUATING, "workflow")
        validity_svc = ValidityService()
        gate_result = validity_svc.evaluate(phi, attribution)  # ValidityGateResult
        # Stored/serialized as a dict below (case.metadata is plain JSON-able
        # storage, and GET /v1/cases/{id}/validity returns it verbatim) — the
        # typed object itself is what ValidityService now returns and what
        # any Python caller should consume directly.
        gate_result_dict = gate_result.model_dump(mode="json")
        case.metadata["gate_result"] = gate_result_dict
        self.cases.save(case)

        gate_artifact = self.praman.register_artifact(
            artifact_type="validity_gate", case_id=case.case_id,
            produced_by="validity_gate", data=gate_result_dict,
        )
        self.event_spine.emit("validity.evaluated", case.case_id, payload={
            "state": gate_result.state.value,
            "allows_action": gate_result.allows_operational_action,
        })

        # Evidence sealed
        self.event_spine.emit("evidence.sealed", case.case_id, payload={
            "scientific_status": ScientificStatus.EXPERIMENTAL.value,
        })

        case.transition(CaseStatus.COMPLETED, "workflow")
        self.event_spine.emit("case.completed", case.case_id)

        return {
            "decision": attribution.decision_state.value,
            "latent_probability": attribution.latent_probability,
            "n_candidates": len(attribution.candidates),
            "gate_state": gate_result.state.value,
            "allows_action": gate_result.allows_operational_action,
            "scientific_status": ScientificStatus.EXPERIMENTAL.value,
        }

    def run_full(self, case_id: str, slick_lons, slick_lats, tracks,
                 obs_time_hours, seed=42, latent_prior=0.5,
                 age_prior_mean=36.0, age_prior_std=24.0) -> dict:
        """Run the entire pipeline end-to-end."""
        t0 = time.time()
        case = self.create_case(case_id)

        case, guard = self.ingest(
            case, slick_lons, slick_lats, tracks, obs_time_hours,
            age_prior_mean, age_prior_std,
        )
        if case.status == CaseStatus.QUARANTINED:
            return {
                "case_id": case.case_id, "status": "quarantined",
                "error": case.error, "runtime_seconds": time.time() - t0,
            }

        phi_result = self.reconstruct(case, seed=seed)
        attr_result = self.attribute(case, latent_prior=latent_prior)

        return {
            "case_id": case.case_id,
            "status": case.status.value,
            "scientific_status": ScientificStatus.EXPERIMENTAL.value,
            "guard_verdict": "accepted",
            "phi_id": phi_result["phi_id"],
            **attr_result,
            "n_artifacts": len(self.praman.list_by_case(case.case_id)),
            "n_events": len(self.event_spine.list_by_case(case.case_id)),
            "runtime_seconds": round(time.time() - t0, 2),
        }
