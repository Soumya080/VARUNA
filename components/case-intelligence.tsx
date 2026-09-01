'use client'

import { ORIGIN, RECOMMENDED_ACTION, SLICK_INFO, formatLat, formatLng } from '@/lib/mock-data'
import { ArrowRight, FileText } from 'lucide-react'
import type { ReactNode } from 'react'
import { CandidateVessels } from './candidate-vessels'
import { EvidenceHealth } from './evidence-health'
import { InfoTip, SectionLabel } from './primitives'

function Panel({
  title,
  tip,
  children,
}: {
  title: string
  tip?: string
  children: ReactNode
}) {
  return (
    <section className="border-b border-border px-3.5 py-3 last:border-b-0">
      <div className="mb-2 flex items-center gap-1.5">
        <SectionLabel>{title}</SectionLabel>
        {tip && <InfoTip label={tip} />}
      </div>
      {children}
    </section>
  )
}

function Row({ label, value }: { label: string; value: ReactNode }) {
  return (
    <div className="flex items-baseline justify-between gap-2 py-0.5">
      <span className="text-[11px] text-muted-foreground">{label}</span>
      <span className="text-right font-mono text-[12px] font-medium tabular-nums text-foreground">
        {value}
      </span>
    </div>
  )
}

export function CaseIntelligence({
  onSelectVessel,
  selectedVesselId,
}: {
  onSelectVessel: (id: string) => void
  selectedVesselId?: string
}) {
  return (
    <aside
      aria-label="Case intelligence"
      className="flex h-full flex-col overflow-hidden rounded-sm border border-border bg-card"
    >
      <div className="flex items-center justify-between border-b border-border bg-muted/40 px-3.5 py-2.5">
        <h2 className="font-mono text-[11px] font-semibold uppercase tracking-[0.14em] text-foreground">
          Case Intelligence
        </h2>
        <span className="font-mono text-[9px] uppercase tracking-[0.1em] text-muted-foreground">
          24-071
        </span>
      </div>

      <div className="flex-1 overflow-y-auto scroll-thin">
        <Panel title="Slick Summary" tip="Oil-slick footprint detected in SAR imagery.">
          <div>
            <Row label="Area" value={SLICK_INFO.area} />
            <Row label="Distance from coast" value={SLICK_INFO.distanceFromCoast} />
            <Row label="Observed" value={SLICK_INFO.observedUtc} />
            <Row label="Estimated age" value={SLICK_INFO.estimatedAge} />
          </div>
        </Panel>

        <Panel
          title="Candidate Vessels"
          tip="Vessels scored by spatiotemporal overlap with the reconstructed origin and release window."
        >
          <CandidateVessels onSelect={onSelectVessel} selectedId={selectedVesselId} />
        </Panel>

        <Panel
          title="Source Estimate"
          tip="Reconstructed release location from the back-trajectory ensemble."
        >
          <Row
            label="Coordinates"
            value={`${formatLat(ORIGIN.point.lat)}, ${formatLng(ORIGIN.point.lng)}`}
          />
          <Row label="Peak likelihood" value={`${ORIGIN.peakLikelihood}%`} />
          <Row label="Estimated release" value={ORIGIN.estimatedRelease} />
        </Panel>

        <Panel title="Recommended Action">
          <p className="text-pretty text-[12px] leading-relaxed text-foreground/90">
            {RECOMMENDED_ACTION}
          </p>
          <button
            type="button"
            className="mt-2.5 flex w-full items-center justify-center gap-1.5 rounded-sm bg-primary px-3 py-2 text-[11px] font-semibold uppercase tracking-[0.08em] text-primary-foreground transition-colors hover:bg-[var(--navy-muted)]"
          >
            <FileText className="h-3.5 w-3.5" />
            View Full Intelligence
            <ArrowRight className="h-3.5 w-3.5" />
          </button>
        </Panel>

        <Panel
          title="Evidence Health"
          tip="Aggregate quality of the data and model outputs supporting this case."
        >
          <EvidenceHealth />
        </Panel>
      </div>
    </aside>
  )
}
