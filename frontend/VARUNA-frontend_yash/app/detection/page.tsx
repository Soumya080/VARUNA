'use client'

import { SLICK_INFO, EVIDENCE_HEALTH } from '@/lib/mock-data'
import { SectionLabel, StatusBadge, Meter } from '@/components/primitives'
import { Check, Radar, Satellite, Eye, Layers, Clock, MapPin, Ruler } from 'lucide-react'

const DETECTION_PARAMS = [
  { label: 'Sensor', value: 'Sentinel-1 SAR (C-band)', status: 'Active' },
  { label: 'Mode', value: 'Interferometric Wide Swath (IW)', status: 'Active' },
  { label: 'Polarization', value: 'VV + VH dual-pol', status: 'Active' },
  { label: 'Resolution', value: '10 m × 10 m', status: 'Active' },
  { label: 'Pass Direction', value: 'Ascending', status: 'Active' },
  { label: 'Incidence Angle', value: '32.4°', status: 'Active' },
]

const CLASSIFICATION_RESULTS = [
  { label: 'Damping Ratio', value: '0.93', score: 93 },
  { label: 'Texture Analysis', value: '0.88', score: 88 },
  { label: 'Edge Detection', value: '0.91', score: 91 },
  { label: 'Shape Irregularity', value: '0.85', score: 85 },
  { label: 'Wind Exclusion', value: '0.96', score: 96 },
]

const DETECTION_TIMELINE = [
  { time: '06:42 UTC', event: 'SAR image acquired — Sentinel-1 ascending pass', status: 'done' },
  { time: '06:43 UTC', event: 'Radiometric calibration and noise floor subtraction', status: 'done' },
  { time: '06:44 UTC', event: 'Dark-spot detection algorithm executed', status: 'done' },
  { time: '06:44 UTC', event: 'ML classifier — oil vs. look-alike discrimination', status: 'done' },
  { time: '06:45 UTC', event: 'Slick footprint segmentation complete', status: 'done' },
  { time: '06:45 UTC', event: 'Detection alert pushed to watch officer', status: 'done' },
]

export default function DetectionPage() {
  return (
    <>
      {/* Page heading */}
      <div className="mb-3 flex flex-wrap items-end justify-between gap-2">
        <div>
          <h1 className="text-balance text-xl font-semibold leading-tight tracking-tight text-foreground sm:text-xl">
            Detection Analysis
          </h1>
          <p className="mt-0.5 font-mono text-[12px] uppercase tracking-[0.1em] text-muted-foreground">
            Case 24-071 · SAR Image Classification · Stage 01
          </p>
        </div>
        <StatusBadge tone="ok" dot>Completed</StatusBadge>
      </div>

      {/* Slick observation summary */}
      <section className="rounded-sm border border-border bg-card p-4">
        <SectionLabel>Slick Observation Summary</SectionLabel>
        <div className="mt-3 grid grid-cols-2 gap-3 sm:grid-cols-4 lg:grid-cols-6">
          {[
            { icon: Clock, label: 'Observed', value: SLICK_INFO.observedUtc },
            { icon: Ruler, label: 'Area', value: SLICK_INFO.area },
            { icon: MapPin, label: 'Dist. from Coast', value: SLICK_INFO.distanceFromCoast },
            { icon: Layers, label: 'Est. Age', value: SLICK_INFO.estimatedAge },
            { icon: Satellite, label: 'Sensor', value: 'Sentinel-1 SAR' },
            { icon: Eye, label: 'Confidence', value: SLICK_INFO.confidence },
          ].map((item) => (
            <div key={item.label} className="rounded-sm border border-border bg-background/60 p-3">
              <div className="flex items-center gap-1.5 mb-1.5">
                <item.icon className="h-3.5 w-3.5 text-saffron" />
                <span className="font-mono text-[10px] uppercase tracking-[0.12em] text-muted-foreground">{item.label}</span>
              </div>
              <span className="font-mono text-[14px] font-semibold text-foreground">{item.value}</span>
            </div>
          ))}
        </div>
      </section>

      {/* SAR Parameters + Classification */}
      <div className="mt-3 grid grid-cols-1 gap-3 lg:grid-cols-2">
        {/* SAR Parameters */}
        <section className="rounded-sm border border-border bg-card p-4">
          <div className="mb-3 flex items-center gap-2">
            <Radar className="h-4 w-4 text-saffron" />
            <SectionLabel>SAR Acquisition Parameters</SectionLabel>
          </div>
          <div className="space-y-0.5">
            {DETECTION_PARAMS.map((param) => (
              <div key={param.label} className="flex items-center justify-between py-1.5 border-b border-border/50 last:border-b-0">
                <span className="text-[13px] text-muted-foreground">{param.label}</span>
                <div className="flex items-center gap-2">
                  <span className="font-mono text-[13px] font-medium text-foreground">{param.value}</span>
                  <span className="h-1.5 w-1.5 rounded-full bg-[var(--ok)]" />
                </div>
              </div>
            ))}
          </div>
        </section>

        {/* Classification Scores */}
        <section className="rounded-sm border border-border bg-card p-4">
          <div className="mb-3 flex items-center gap-2">
            <Eye className="h-4 w-4 text-teal" />
            <SectionLabel>Classification Scores</SectionLabel>
          </div>
          <div className="space-y-3">
            {CLASSIFICATION_RESULTS.map((item) => (
              <div key={item.label}>
                <div className="flex items-center justify-between mb-1">
                  <span className="text-[13px] text-muted-foreground">{item.label}</span>
                  <span className="font-mono text-[13px] font-semibold text-foreground">{item.value}</span>
                </div>
                <Meter value={item.score} tone={item.score >= 90 ? 'teal' : 'saffron'} />
              </div>
            ))}
          </div>
          <div className="mt-4 rounded-sm border border-[color-mix(in_oklch,var(--ok)_35%,transparent)] bg-[color-mix(in_oklch,var(--ok)_8%,transparent)] p-3">
            <div className="flex items-center gap-2">
              <Check className="h-4 w-4 text-[var(--ok)]" />
              <span className="font-mono text-[12px] font-semibold uppercase tracking-[0.08em] text-[color-mix(in_oklch,var(--ok)_60%,black)]">
                Oil slick confirmed — Look-alike excluded
              </span>
            </div>
            <p className="mt-1 text-[12px] text-muted-foreground">
              Combined classifier score 0.91 exceeds threshold (0.75). Natural phenomena and ship-wake artifacts ruled out.
            </p>
          </div>
        </section>
      </div>

      {/* Detection Timeline */}
      <section className="mt-3 rounded-sm border border-border bg-card p-4">
        <SectionLabel>Detection Timeline</SectionLabel>
        <div className="mt-3 relative">
          <div className="absolute left-[7px] top-3 bottom-3 w-px bg-border" />
          <div className="space-y-3">
            {DETECTION_TIMELINE.map((item, i) => (
              <div key={i} className="flex items-start gap-3 relative">
                <span className="relative z-10 grid h-4 w-4 shrink-0 place-items-center rounded-full bg-[var(--ok)] text-white mt-0.5">
                  <Check className="h-2.5 w-2.5" />
                </span>
                <div className="flex-1 flex items-baseline justify-between gap-2">
                  <span className="text-[13px] text-foreground">{item.event}</span>
                  <span className="shrink-0 font-mono text-[11px] text-muted-foreground">{item.time}</span>
                </div>
              </div>
            ))}
          </div>
        </div>
      </section>
    </>
  )
}
