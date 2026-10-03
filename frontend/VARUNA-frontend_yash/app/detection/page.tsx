'use client'

/**
 * Phase 9 (docs/product/HONESTY_LEDGER.md #26): converted from a fully
 * hardcoded mock page (SLICK_INFO/DETECTION_PARAMS/CLASSIFICATION_RESULTS/
 * DETECTION_TIMELINE, all fabricated) to real data. `oc.detection` (NETRA's
 * real output) and `oc.observation` (the real ingest input) are the only
 * two things this page can honestly show — there is no per-parameter SAR
 * acquisition metadata (polarization, incidence angle, etc.) anywhere in
 * VARUNA's contracts, so that section is gone rather than kept fabricated.
 * Anything the backend didn't produce says NOT_YET_PRODUCED with its
 * reason, per the Phase 9 conversion rule.
 */
import { SectionLabel, StatusBadge, Meter } from '@/components/primitives'
import { Row } from '@/components/cockpit/cockpit-panels'
import { OperatorCaseProvider, useOperatorCaseData } from '@/lib/operator-case-context'
import { OperatorCaseBoundary } from '@/components/operator-case-boundary'
import { EvidenceModeBadge } from '@/components/evidence-mode-badge'
import { Check, Radar, Satellite, Eye, Layers, Clock, MapPin, Ruler } from 'lucide-react'

const DEFAULT_FIXTURE = 'IND-CASE-01'

function DetectionBody() {
  const oc = useOperatorCaseData()
  if (!oc) return null
  const det = oc.detection
  const obs = oc.observation

  return (
    <>
      <div className="mb-3 flex flex-wrap items-end justify-between gap-2">
        <div>
          <h1 className="text-balance text-xl font-semibold leading-tight tracking-tight text-foreground sm:text-xl">
            Detection Analysis
          </h1>
          <p className="mt-0.5 font-mono text-[12px] uppercase tracking-[0.1em] text-muted-foreground">
            {oc.case_id} · NETRA SAR classification
          </p>
        </div>
        <div className="flex items-center gap-1.5">
          <EvidenceModeBadge mode={det.evidence_mode} />
          <StatusBadge tone={det.status === 'produced' ? 'ok' : 'muted'} dot>
            {det.status.replace(/_/g, ' ')}
          </StatusBadge>
        </div>
      </div>

      {det.status !== 'produced' || !det.value ? (
        <section className="rounded-sm border border-border bg-card p-4">
          <p className="text-[13px] text-muted-foreground">
            {det.reason ?? 'No detection has been produced for this case.'}
          </p>
        </section>
      ) : (
        <>
          <section className="rounded-sm border border-border bg-card p-4">
            <SectionLabel>Slick Observation Summary</SectionLabel>
            <div className="mt-3 grid grid-cols-2 gap-3 sm:grid-cols-4 lg:grid-cols-6">
              {[
                {
                  icon: Clock,
                  label: 'Observed',
                  value: obs.status === 'produced' && obs.value?.observation_time
                    ? new Date(obs.value.observation_time).toISOString().slice(0, 16).replace('T', ' ') + 'Z'
                    : '—',
                },
                { icon: Ruler, label: 'Area', value: `${det.value.area_km2.toFixed(1)} km²` },
                { icon: Layers, label: 'Perimeter', value: `${det.value.perimeter_km.toFixed(1)} km` },
                { icon: Layers, label: 'Elongation', value: det.value.elongation.toFixed(2) },
                { icon: Satellite, label: 'Model', value: det.value.netra_model_version },
                { icon: Eye, label: 'Confidence', value: `${(det.value.confidence * 100).toFixed(0)}%` },
              ].map((item) => (
                <div key={item.label} className="rounded-sm border border-border bg-background/60 p-3">
                  <div className="mb-1.5 flex items-center gap-1.5">
                    <item.icon className="h-3.5 w-3.5 text-saffron" />
                    <span className="font-mono text-[10px] uppercase tracking-[0.12em] text-muted-foreground">
                      {item.label}
                    </span>
                  </div>
                  <span className="font-mono text-[14px] font-semibold text-foreground">{item.value}</span>
                </div>
              ))}
            </div>
          </section>

          <div className="mt-3 grid grid-cols-1 gap-3 lg:grid-cols-2">
            <section className="rounded-sm border border-border bg-card p-4">
              <div className="mb-3 flex items-center gap-2">
                <Radar className="h-4 w-4 text-saffron" />
                <SectionLabel>Detection Geometry</SectionLabel>
              </div>
              <div className="space-y-0.5">
                <Row label="Classification" value={det.value.classification} />
                <Row label="Look-alike type" value={det.value.look_alike_type ?? 'not flagged'} />
                <Row
                  label="Centroid"
                  value={det.value.centroid ? `${det.value.centroid.lat.toFixed(3)}, ${det.value.centroid.lon.toFixed(3)}` : '—'}
                />
                <Row label="Orientation" value={`${det.value.orientation_deg.toFixed(1)}°`} />
                <Row
                  label="Age prior"
                  value={`${det.value.age_prior_mean_hours.toFixed(0)}h ± ${det.value.age_prior_std_hours.toFixed(0)}h`}
                />
                <Row label="Mean wind speed" value={det.value.mean_wind_speed_ms != null ? `${det.value.mean_wind_speed_ms.toFixed(1)} m/s` : 'not measured'} />
                <Row label="Scene" value={det.value.scene_id} />
              </div>
            </section>

            <section className="rounded-sm border border-border bg-card p-4">
              <div className="mb-3 flex items-center gap-2">
                <Eye className="h-4 w-4 text-teal" />
                <SectionLabel>Classification confidence</SectionLabel>
              </div>
              <div>
                <div className="mb-1 flex items-center justify-between">
                  <span className="text-[13px] text-muted-foreground">NETRA confidence</span>
                  <span className="font-mono text-[13px] font-semibold text-foreground">
                    {(det.value.confidence * 100).toFixed(0)}%
                  </span>
                </div>
                <Meter value={det.value.confidence * 100} tone={det.value.confidence >= 0.8 ? 'teal' : 'saffron'} />
              </div>
              <p className="mt-3 text-[11px] leading-snug text-muted-foreground">
                This is NETRA's own reported confidence — a single real number, not a
                multi-factor classifier breakdown. VARUNA does not compute per-signal scores
                (damping ratio, texture, edge detection, etc.) anywhere in its pipeline; a
                page that showed those would be fabricating them.
              </p>
              {det.value.classification === 'oil' ? (
                <div className="mt-4 rounded-sm border border-[color-mix(in_oklch,var(--ok)_35%,transparent)] bg-[color-mix(in_oklch,var(--ok)_8%,transparent)] p-3">
                  <div className="flex items-center gap-2">
                    <Check className="h-4 w-4 text-[var(--ok)]" />
                    <span className="font-mono text-[12px] font-semibold uppercase tracking-[0.08em] text-[color-mix(in_oklch,var(--ok)_60%,black)]">
                      Classified as oil
                    </span>
                  </div>
                </div>
              ) : (
                <div className="mt-4 rounded-sm border border-border bg-muted/30 p-3">
                  <span className="font-mono text-[12px] font-semibold uppercase tracking-[0.08em] text-muted-foreground">
                    Classified as {det.value.classification}
                  </span>
                </div>
              )}
            </section>
          </div>
        </>
      )}
    </>
  )
}

export default function DetectionPage() {
  return (
    <OperatorCaseProvider fixtureName={DEFAULT_FIXTURE}>
      <OperatorCaseBoundary>
        <DetectionBody />
      </OperatorCaseBoundary>
    </OperatorCaseProvider>
  )
}
