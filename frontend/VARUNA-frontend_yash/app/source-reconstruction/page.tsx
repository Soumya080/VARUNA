'use client'

/**
 * Phase 9 (docs/product/HONESTY_LEDGER.md #26): converted from a fully
 * hardcoded mock page (ORIGIN/PARTICLE_TRAJECTORIES/FORCING_DATA/
 * DRIFT_PARAMETERS/UNCERTAINTY, all fabricated — including a fake origin
 * lat/lon with a fake "peak likelihood") to real data from `oc.origin`
 * (PRATIVARTAN's real `PhiField` — diagnostics + the real per-parameter
 * `SensitivityBlock`). Honest finding: none of the replay fixtures'
 * `spatial_modes` are populated (the backward reconstruction produces a
 * probability FIELD, not a single point estimate, for any demo case) — so
 * "reconstructed origin point" honestly says NOT_YET_PRODUCED rather than
 * inventing a lat/lon, instead of the mock page's fabricated coordinate.
 */
import { SectionLabel, StatusBadge, Meter } from '@/components/primitives'
import { Row } from '@/components/cockpit/cockpit-panels'
import { OperatorCaseProvider, useOperatorCaseData } from '@/lib/operator-case-context'
import { OperatorCaseBoundary } from '@/components/operator-case-boundary'
import { EvidenceModeBadge } from '@/components/evidence-mode-badge'
import { Waypoints, Wind, Target, Gauge } from 'lucide-react'

const DEFAULT_FIXTURE = 'IND-CASE-01'

interface PhiDiagnostics {
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

interface SpatialMode {
  centroid: { lon: number; lat: number }
  mass: number
  area_km2: number
  peak_time_unix: number
}

interface SensitivityBlock {
  age_sensitivity: number | null
  forcing_sensitivity: number | null
  diffusivity_sensitivity: number | null
  weathering_sensitivity: number | null
}

interface PhiFieldValue {
  phi_id: string
  n_particles: number
  n_ensemble: number
  backward_duration_hours: number
  dt_seconds: number
  forcing_current_source: string
  forcing_wind_source: string
  weathering_model: string | null
  diagnostics: PhiDiagnostics
  spatial_modes: SpatialMode[]
  sensitivity: SensitivityBlock
}

function SensitivityRow({ label, value }: { label: string; value: number | null }) {
  return (
    <div>
      <div className="mb-1 flex items-center justify-between">
        <span className="text-[13px] text-muted-foreground">{label}</span>
        <span className="font-mono text-[13px] font-medium text-foreground">
          {value != null ? value.toFixed(2) : 'not measured'}
        </span>
      </div>
      <Meter value={value != null ? value * 100 : 0} tone={value != null && value > 0.2 ? 'saffron' : 'teal'} />
    </div>
  )
}

function SourceReconstructionBody() {
  const oc = useOperatorCaseData()
  if (!oc) return null
  const origin = oc.origin
  const phi = origin.status === 'produced' ? (origin.value as unknown as PhiFieldValue) : null
  const topMode = phi?.spatial_modes.length ? phi.spatial_modes.slice().sort((a, b) => b.mass - a.mass)[0] : null

  return (
    <>
      <div className="mb-3 flex flex-wrap items-end justify-between gap-2">
        <div>
          <h1 className="text-balance text-xl font-semibold leading-tight tracking-tight text-foreground sm:text-xl">
            Source Reconstruction
          </h1>
          <p className="mt-0.5 font-mono text-[12px] uppercase tracking-[0.1em] text-muted-foreground">
            {oc.case_id} · PRATIVARTAN (Φ) backward reconstruction
          </p>
        </div>
        <div className="flex items-center gap-1.5">
          <EvidenceModeBadge mode={origin.evidence_mode} />
          <StatusBadge tone={origin.status === 'produced' ? 'ok' : 'muted'} dot>
            {origin.status.replace(/_/g, ' ')}
          </StatusBadge>
        </div>
      </div>

      {!phi ? (
        <section className="rounded-sm border border-border bg-card p-4">
          <p className="text-[13px] text-muted-foreground">
            {origin.reason ?? 'No backward reconstruction has been produced for this case.'}
          </p>
        </section>
      ) : (
        <>
          <section className="rounded-sm border border-saffron/30 bg-saffron/5 p-4">
            <div className="mb-3 flex items-center gap-2">
              <Target className="h-4 w-4 text-saffron" />
              <SectionLabel className="text-saffron">Reconstructed Origin</SectionLabel>
            </div>
            {topMode ? (
              <div className="grid grid-cols-2 gap-3 sm:grid-cols-4 lg:grid-cols-5">
                <div className="rounded-sm border border-saffron/20 bg-card p-3">
                  <div className="mb-1 font-mono text-[10px] uppercase tracking-[0.1em] text-muted-foreground">Latitude</div>
                  <div className="font-mono text-[16px] font-bold text-foreground">{topMode.centroid.lat.toFixed(3)}°</div>
                </div>
                <div className="rounded-sm border border-saffron/20 bg-card p-3">
                  <div className="mb-1 font-mono text-[10px] uppercase tracking-[0.1em] text-muted-foreground">Longitude</div>
                  <div className="font-mono text-[16px] font-bold text-foreground">{topMode.centroid.lon.toFixed(3)}°</div>
                </div>
                <div className="rounded-sm border border-saffron/20 bg-card p-3">
                  <div className="mb-1 font-mono text-[10px] uppercase tracking-[0.1em] text-muted-foreground">Mode mass</div>
                  <div className="font-mono text-[16px] font-bold text-saffron">{(topMode.mass * 100).toFixed(0)}%</div>
                </div>
                <div className="rounded-sm border border-saffron/20 bg-card p-3">
                  <div className="mb-1 font-mono text-[10px] uppercase tracking-[0.1em] text-muted-foreground">Support area</div>
                  <div className="font-mono text-[16px] font-bold text-foreground">
                    {phi.diagnostics.effective_support_km2.toFixed(0)} km²
                  </div>
                </div>
                <div className="rounded-sm border border-saffron/20 bg-card p-3">
                  <div className="mb-1 font-mono text-[10px] uppercase tracking-[0.1em] text-muted-foreground">Modes</div>
                  <div className="font-mono text-[16px] font-bold text-foreground">{phi.diagnostics.n_modes}</div>
                </div>
              </div>
            ) : (
              <p className="text-[13px] text-muted-foreground">
                No spatial mode was resolved to a single point estimate for this case — the
                backward reconstruction produced a probability field (see diagnostics below),
                not a point release location. This is the honest state, not a missing feature:
                inventing a coordinate here would misrepresent what Φ actually computed.
              </p>
            )}
          </section>

          <div className="mt-3 grid grid-cols-1 gap-3 lg:grid-cols-2">
            <section className="rounded-sm border border-border bg-card p-4">
              <div className="mb-3 flex items-center gap-2">
                <Waypoints className="h-4 w-4 text-teal" />
                <SectionLabel>Ensemble & Reconstruction Parameters</SectionLabel>
              </div>
              <div className="space-y-0.5">
                <Row label="Particles" value={`${phi.n_particles} seeded, ${phi.n_ensemble} ensemble members`} />
                <Row label="Ensemble completed" value={`${phi.diagnostics.ensemble_members_completed} / ${phi.diagnostics.ensemble_members_requested}`} />
                <Row label="Particles lost" value={`${phi.diagnostics.particles_lost} of ${phi.diagnostics.particles_seeded}`} />
                <Row label="Backward window" value={`${phi.backward_duration_hours.toFixed(1)}h, dt=${phi.dt_seconds.toFixed(0)}s`} />
                <Row label="Runtime" value={`${phi.diagnostics.runtime_seconds.toFixed(1)}s`} />
                <Row label="Convergence" value={phi.diagnostics.convergence_flag.replace(/_/g, ' ')} />
                <Row label="Multimodal" value={phi.diagnostics.multimodal ? 'yes' : 'no'} />
              </div>
            </section>

            <section className="rounded-sm border border-border bg-card p-4">
              <div className="mb-3 flex items-center gap-2">
                <Wind className="h-4 w-4 text-saffron" />
                <SectionLabel>Forcing Sources</SectionLabel>
              </div>
              <div className="space-y-0.5">
                <Row label="Current forcing" value={phi.forcing_current_source} />
                <Row label="Wind forcing" value={phi.forcing_wind_source} />
                <Row label="Weathering model" value={phi.weathering_model ?? 'not applied'} />
              </div>
              <p className="mt-3 text-[11px] leading-snug text-muted-foreground">
                VARUNA does not carry per-source coverage percentages, wave/tide model
                identifiers, or SST analysis products anywhere in its contracts — these are the
                only forcing-provenance fields the pipeline actually records.
              </p>
            </section>
          </div>

          <section className="mt-3 rounded-sm border border-border bg-card p-4">
            <div className="mb-3 flex items-center gap-2">
              <Gauge className="h-4 w-4 text-teal" />
              <SectionLabel>Real Per-Parameter Sensitivity</SectionLabel>
            </div>
            <div className="grid grid-cols-1 gap-3 sm:grid-cols-2">
              <SensitivityRow label="Age sensitivity" value={phi.sensitivity.age_sensitivity} />
              <SensitivityRow label="Forcing sensitivity" value={phi.sensitivity.forcing_sensitivity} />
              <SensitivityRow label="Diffusivity sensitivity" value={phi.sensitivity.diffusivity_sensitivity} />
              <SensitivityRow label="Weathering sensitivity" value={phi.sensitivity.weathering_sensitivity} />
            </div>
            <p className="mt-3 text-[11px] leading-snug text-muted-foreground">
              A real per-parameter uncertainty decomposition (`SensitivityBlock`), not a
              fabricated per-source uncertainty table. Each value is how much the
              reconstruction's outcome moves when that one input is perturbed — "not measured"
              means the sensitivity sweep for that parameter did not run for this case, not
              zero sensitivity.
            </p>
          </section>

          <section className="mt-3 rounded-sm border border-border bg-card p-4">
            <SectionLabel>Reconstruction Diagnostics</SectionLabel>
            <div className="mt-2 grid grid-cols-2 gap-x-4 sm:grid-cols-3">
              <Row label="Entropy" value={phi.diagnostics.entropy.toFixed(2)} />
              <Row label="Concentration" value={phi.diagnostics.concentration.toFixed(2)} />
              <Row label="Boundary interaction" value={phi.diagnostics.boundary_interaction ? 'yes' : 'no'} />
            </div>
          </section>
        </>
      )}
    </>
  )
}

export default function SourceReconstructionPage() {
  return (
    <OperatorCaseProvider fixtureName={DEFAULT_FIXTURE}>
      <OperatorCaseBoundary>
        <SourceReconstructionBody />
      </OperatorCaseBoundary>
    </OperatorCaseProvider>
  )
}
