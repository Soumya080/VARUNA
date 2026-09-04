"""Phase 5B regression lock (docs/product/HONESTY_LEDGER.md).

`frontend/.../components/cockpit/chhaya-panel.tsx`'s `Candidate` TypeScript
interface is hand-synced to `CandidateEvidenceRecord` below — there is no
shared-schema codegen in this repo, so nothing enforces that sync
automatically. This test cannot see the TypeScript file, but it pins the
Python side of the contract: if a field this test asserts is removed or
renamed, the frontend interface goes stale again in exactly the way that
let a real detection crash the panel before this fix (`vessel_score`,
`geolocation_valid`, `position`, etc. never actually existed on the wire).

Whoever changes `CandidateEvidenceRecord` should grep the frontend file for
each field name touched here before this test is trusted to have caught it.
"""
from varuna_chhaya.v2.nyaya_handoff import CandidateEvidenceRecord

# The exact field set `chhaya-panel.tsx`'s `Candidate` interface expects on
# the wire, mirrored 1:1 with the frontend interface's own field list.
FRONTEND_CANDIDATE_FIELDS = {
    "candidate_id",
    "sar_vessel_score",
    "sar_score_type",
    "ais_state",
    "ais_distance_km",
    "origin_spatial_consistency",
    "origin_temporal_consistency",
    "course_consistency",
    "speed_consistency",
    "relative_plausibility",
    "rank",
    "missing_evidence",
    "position",
    "geolocation_valid",
    "geolocation_rejection_reason",
}


def test_candidate_evidence_record_has_every_field_the_frontend_reads():
    model_fields = set(CandidateEvidenceRecord.model_fields.keys())
    missing = FRONTEND_CANDIDATE_FIELDS - model_fields
    assert not missing, (
        f"chhaya-panel.tsx's Candidate interface reads fields not on "
        f"CandidateEvidenceRecord: {sorted(missing)} — the frontend will "
        f"render undefined/crash for these"
    )


def test_candidate_evidence_record_has_no_undocumented_extra_fields():
    """Not strictly required for correctness, but a model field the
    frontend doesn't know about is exactly the kind of drift that produces
    a silently-stale UI. Keep this list updated deliberately, not
    accidentally."""
    model_fields = set(CandidateEvidenceRecord.model_fields.keys())
    extra = model_fields - FRONTEND_CANDIDATE_FIELDS
    assert not extra, (
        f"CandidateEvidenceRecord has fields the frontend Candidate "
        f"interface doesn't read: {sorted(extra)} — either the frontend is "
        f"missing real data, or this test's field list needs updating"
    )
