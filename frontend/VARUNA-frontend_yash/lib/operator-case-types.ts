/**
 * TypeScript mirror of `varuna_contracts.operator_case.OperatorCase`
 * (packages/varuna_contracts/operator_case.py, schema "v1").
 *
 * Deliberately loose where the backend itself is loose (e.g. `memory_hits`
 * and `evidence_lineage` are plain records upstream too — see
 * IntelligenceSection's own docstring in operator_case.py for why). Every
 * other field mirrors the backend's Pydantic model shape exactly, since this
 * file's only job is to describe what `GET /v1/replay/{fixture}` and
 * `GET /v1/cases/{id}/operator-view` actually return — never to invent a
 * shape the backend doesn't produce.
 */

export type ProducerStatus = 'not_yet_produced' | 'produced' | 'blocked'
export type EvidenceModeValue = 'real' | 'simulated' | 'unavailable'
export type EngineModeValue = 'real' | 'replay' | 'simulated' | null

export interface SectionEnvelope<T> {
  status: ProducerStatus
  reason: string | null
  evidence_mode: EvidenceModeValue | null
  value: T | null
}

export interface SystemStatusView {
  case_status: string
  scientific_status: string
  error: string | null
  engine_mode: EngineModeValue
}

export interface ObservationView {
  n_slick_points: number
  n_tracks: number
  // M3 fix (docs/product/HONESTY_LEDGER.md #5): the backend field was
  // renamed from `obs_time_hours` to `phi_time_coordinate_hours` —
  // it is Phi's internal epoch-relative coordinate (can be legitimately
  // negative for a historical reconstruction), not an elapsed-hours value,
  // and was being shown to operators as if it were one. `observation_time`
  // is the new field carrying the real wall-clock time; it's the one to
  // show an operator, with `phi_time_coordinate_hours` as a tooltipped
  // detail (see ObservationView's Python docstring for the full story).
  phi_time_coordinate_hours: number
  observation_time: string | null
  bbox: BBoxValue | null
}

export interface BBoxValue {
  min_lon: number
  min_lat: number
  max_lon: number
  max_lat: number
}

export interface SlickDetectionValue {
  slick_id: string
  scene_id: string
  observation_time: string
  classification: string
  confidence: number
  look_alike_type: string | null
  centroid: { lon: number; lat: number } | null
  bbox: BBoxValue | null
  area_km2: number
  perimeter_km: number
  elongation: number
  orientation_deg: number
  age_prior_mean_hours: number
  age_prior_std_hours: number
  mean_wind_speed_ms: number | null
  netra_model_version: string
  [key: string]: unknown
}

export interface AISCandidateView {
  mmsi: string
  vessel_name: string | null
  vessel_type: string | null
  n_points: number
  start_time: string
  end_time: string
  total_gap_minutes: number
  max_gap_minutes: number
  transponder_active: boolean
}

export interface AttributionCandidate {
  rank: number
  mmsi: string
  posterior: number
}

export interface HistoricalReconstruction {
  vessel_name: string
  mmsi: string | null
  event_description: string
  source_citation: string
  provenance: 'historical_record_not_computed_by_varuna'
}

export interface AttributionResultValue {
  decision_state: string
  latent_probability: number
  latent_finding: string
  top_posterior: number
  distinguishability: number
  posterior_entropy: number
  candidates: AttributionCandidate[]
  // M1+M2 fix (docs/product/HONESTY_LEDGER.md #3-4): a real-world vessel
  // identity VARUNA did NOT compute — structurally separate from
  // `candidates`, never a score. See HistoricalReconstruction's own
  // docstring on the Python side (packages/varuna_contracts/decision.py).
  historical_reconstruction: HistoricalReconstruction | null
  [key: string]: unknown
}

export interface ValidityGateResultValue {
  state: string
  // NOTE: `allows_operational_action` is deliberately absent. It is a Python
  // @property on the ValidityState enum and is never serialised — declaring
  // it here previously caused a VALID gate to render as "does not allow
  // operational action". Derive it from `state` (valid | degraded) instead.
  blocking_reasons?: string[]
  officer_visible_caveats?: string[]
  checks: Array<{
    name: string
    passed: boolean
    reason_code: string | null
    message: string | null
    blocking: boolean
  }>
  [key: string]: unknown
}

export interface LandfallPrediction {
  location_name: string
  position: { lon: number; lat: number }
  eta: string
  hours_until: number
  probability: number
  coastline_segment_km: number
}

export interface ForwardForecastValue {
  forecast_id: string
  slick_id: string
  horizon_hours: number
  landfalls: LandfallPrediction[]
  affected_fishing_zones: string[]
  trajectory_path: string
  computed_at: string
  envelope: { mode: EvidenceModeValue; case_id: string | null; [key: string]: unknown }
}

/** ADR-0017 — one point on the derived backward-drift centroid path. */
export interface BackdriftPathPoint {
  time_hours: number   // hours before observation (age) — always >= 0
  lon: number
  lat: number
  mass_fraction: number // this time-slice's share of total Phi mass
}

/** Mirrors `varuna_contracts.phi.PhiField` — the complete origin-probability artifact. */
export interface PhiFieldValue {
  phi_id: string
  slick_id: string
  case_id: string
  data_path: string
  bbox: BBoxValue
  grid_shape: [number, number, number]
  n_particles: number
  n_ensemble: number
  backward_duration_hours: number
  dt_seconds: number
  forcing_current_source: string
  forcing_wind_source: string
  weathering_model: string | null
  diagnostics: {
    entropy: number
    concentration: number
    effective_support_km2: number
    convergence: number
    convergence_flag: string
    n_modes: number
    multimodal: boolean
    boundary_interaction: boolean
    particles_lost: number
    particles_seeded: number
    ensemble_members_completed: number
    ensemble_members_requested: number
    runtime_seconds: number
  }
  sensitivity: {
    age_sensitivity: number
    forcing_sensitivity: number
    diffusivity_sensitivity: number
    weathering_sensitivity: number | null
  } | null
  /** ADR-0017. Null = not computed, never "computed and empty". */
  backdrift_path: BackdriftPathPoint[] | null
  spatial_modes: Array<{ centroid: { lon: number; lat: number }; mass: number; area_km2: number; peak_time_unix: number; separation_km: number | null }>
  time_distribution: { time_edges_unix: number[]; mass: number[]; mode_unix: number; p05_unix: number; p95_unix: number }
  envelope: { mode: EvidenceModeValue; [key: string]: unknown }
  [key: string]: unknown
}

export interface AssetTaskingValue {
  [key: string]: unknown
}

export interface SearchBoxValue {
  bbox: BBoxValue
  center: { lon: number; lat: number }
  area_km2: number
  phi_mass_contained: number
}

export interface AssetTaskingDetail {
  asset_type: string
  base_name: string
  search_box: SearchBoxValue
  pattern: string
  launch_time: string
  flight_hours: number
  probability_of_detection: number
  rationale: string
}

export interface MissionRecordValue {
  mission_id: string
  state: string
  asset_id: string | null
  // Fix: the real wire field is `human_approved_by` (see
  // `varuna_contracts.states.MissionRecord`) — this type previously
  // declared `approved_by`, which never existed on the wire and made
  // every "who approved this" display silently render undefined/falsy,
  // including `components/verification-ledger.tsx`'s Human Authorization
  // axis (found while wiring MissionRecord.tasking onto the map, Phase 9).
  human_approved_by: string | null
  // Real tasking, ADR-0015 — search box, pattern, launch time, PoD,
  // rationale. Was computed and thrown away before that ADR; now stored
  // and available here for the map to actually draw.
  tasking?: AssetTaskingDetail | null
  [key: string]: unknown
}

export interface AlertView {
  channel: string
  recipient: string
  category: string | null
  delivery_status: string
  severity: string
  reason: string | null
  is_simulated: boolean
  timestamp: string
}

export type OperationalDecisionState =
  | 'valid'
  | 'degraded'
  | 'restricted'
  | 'inconclusive'
  | 'unavailable'

export interface EvidenceComponentView {
  component: string
  status: ProducerStatus
  score: number | null
  reason: string | null
  evidence_mode: EvidenceModeValue | null
  observed_at: string | null
}

export interface EvidenceHealthView {
  components: EvidenceComponentView[]
}

export interface ProvenanceView {
  case_id: string
  artifact_ids: string[]
  source_ids: string[]
  model_versions: Record<string, string>
  processing_versions: Record<string, string>
  manifest_artifact_id: string | null
  generated_at: string
}

/* ---------------------------- Intelligence ---------------------------- */

export interface MeasuredValue {
  value: number | null
  status: 'measured' | 'inferred' | 'simulated' | 'replayed' | 'unavailable'
  units: string | null
  note: string | null
}

export interface UncertaintyAssessmentValue {
  case_id: string
  model_confidence: MeasuredValue | null
  data_quality: MeasuredValue | null
  ood_risk: 'in_domain' | 'borderline' | 'out_of_domain' | 'unknown'
  evidence_agreement: MeasuredValue | null
  evidence_conflict_count: number
  attribution_uncertainty: MeasuredValue | null
  forecast_uncertainty: MeasuredValue | null
  decision_confidence: MeasuredValue | null
  component_notes: Record<string, string>
}

export interface FactorContribution {
  factor: string
  detail: string
  // >0 supports, <0 opposes, 0 neutral — see
  // packages/varuna_contracts/source_hypothesis.py::FactorContribution.
  log_likelihood_ratio: number
  evidence_ids: string[]
  // False = a declared assumption, not measured data — the honesty
  // affordance the hypothesis waterfall (Phase 10) exists to surface.
  measured: boolean
}

export interface SourceHypothesisValue {
  source_class: string
  prior: number
  posterior: number
  // Fix: this type previously declared `supporting`/`against` with an
  // invented FactorContribution shape (`direction`/`weight`/`note`) that
  // never matched the wire (`supporting`/`contradicting`,
  // `log_likelihood_ratio`, `measured`) — never caught because nothing
  // consumed per-factor detail before Phase 10's hypothesis waterfall.
  supporting: FactorContribution[]
  contradicting: FactorContribution[]
  rationale: string
}

export interface SourceHypothesisEnvelopeValue {
  case_id: string
  method: 'declared_likelihood_ratio' | string
  methodology_note: string
  hypotheses: SourceHypothesisValue[]
  // NOTE: the backend's `.top` is a plain Python @property, not a
  // @computed_field -- it is NEVER present in the serialized JSON (found
  // during STEP 5's runtime diagnostic). Derive the top hypothesis with
  // `hypotheses.reduce/sort` on the client, as intelligence-panels.tsx
  // already does. Deliberately not declared as a field here so this type
  // never encourages code to read a key that does not exist at runtime.
  n_factors_considered: number
  evidence_ids_considered: string[]
  contradictions: string[]
  insufficient_evidence: boolean
  envelope: { mode: EvidenceModeValue; [key: string]: unknown }
  [key: string]: unknown
}

export interface NextBestActionValue {
  action_id: string
  case_id: string
  kind: string
  because: string
  targets_uncertainty: string
  required_evidence: string[]
  expected_effect: string
  priority: number
  selected_at: string
}

export interface DecisionStepValue {
  iteration: number
  phase: string
  note: string
  action: NextBestActionValue | null
  record: {
    outcome: string
    result_summary: string
    evidence_added: string[]
    changed: boolean
    error: string | null
  } | null
  dominant_concern: string | null
  at: string
}

export interface DecisionTraceValue {
  case_id: string
  steps: DecisionStepValue[]
  terminal_action: string | null
  terminal_reason: string | null
  iterations: number
  halted_on_budget: boolean
}

export interface MemoryHit {
  case_id: string
  score: number
  coverage: number
  outcome: string | null
  provenance_source: string
  [key: string]: unknown
}

export interface EvidenceLedgerItem {
  evidence_id: string
  kind: string
  produced_by: string
  summary: string
  mode: EvidenceModeValue
  confidence: number | null
  status: string
  revision?: number
  recorded_at?: string
  depends_on: string[]
  contradicts?: string[]
  superseded_by?: string | null
  [key: string]: unknown
}

export interface IntelligenceSection {
  status: ProducerStatus
  reason: string | null
  uncertainty: UncertaintyAssessmentValue | null
  hypotheses: SourceHypothesisEnvelopeValue | null
  memory_hits: MemoryHit[]
  decision_trace: DecisionTraceValue | null
  next_best_action: NextBestActionValue | null
  evidence_lineage: EvidenceLedgerItem[]
}

/* --------------------------- Starting point --------------------------- */

/** Mirrors varuna_contracts.operator_case.StartingPoint. The single explicit
 * answer to "where did this spill start?". `UNKNOWN_NO_LANDMASK` must never
 * be rendered as "confirmed at sea" — the repository ships no land mask. */
export type StartingPointStatus =
  | 'STARTING_POINT_AVAILABLE'
  | 'STARTING_POINT_UNAVAILABLE'
  | 'STARTING_POINT_INVALID'
  | 'STARTING_POINT_REJECTED_LAND'

export interface StartingPoint {
  status: StartingPointStatus
  source: 'detection_centroid' | 'phi_bbox_center' | 'none'
  point: { lon: number; lat: number } | null
  land_classification: 'water' | 'land' | 'unknown_no_landmask'
  reason: string | null
  evidence_mode: EvidenceModeValue | null
}

/* ------------------------------ Root ------------------------------ */

export interface OperatorCase {
  schema_version: string
  case_id: string
  generated_at: string
  system_status: SystemStatusView
  observation: SectionEnvelope<ObservationView>
  detection: SectionEnvelope<SlickDetectionValue>
  origin: SectionEnvelope<PhiFieldValue>
  ais: SectionEnvelope<AISCandidateView[]>
  attribution: SectionEnvelope<AttributionResultValue>
  validity: SectionEnvelope<ValidityGateResultValue>
  forecast: SectionEnvelope<ForwardForecastValue>
  decision: SectionEnvelope<AssetTaskingValue[]>
  mission: SectionEnvelope<MissionRecordValue[]>
  alerts: SectionEnvelope<AlertView[]>
  starting_point: StartingPoint
  recommendation: OperationalDecisionState
  evidence: EvidenceHealthView
  provenance: ProvenanceView
  intelligence: IntelligenceSection
}
