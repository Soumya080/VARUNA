'use client'

import { VESSELS } from '@/lib/mock-data'
import { SectionLabel, StatusBadge, Meter } from '@/components/primitives'
import { Ship, Anchor, Navigation, Radio, Clock, MapPin, AlertTriangle, Check, ChevronRight } from 'lucide-react'
import { cn } from '@/lib/utils'
import { useState } from 'react'

function roleTone(role: string) {
  if (role === 'PRIMARY LEAD') return 'saffron' as const
  if (role === 'ALTERNATE') return 'warn' as const
  return 'muted' as const
}

export default function VesselAttributionPage() {
  const [expandedId, setExpandedId] = useState<string | null>('v1')

  return (
    <>
      <div className="mb-3 flex flex-wrap items-end justify-between gap-2">
        <div>
          <h1 className="text-balance text-lg font-semibold leading-tight tracking-tight text-foreground sm:text-xl">
            Vessel Attribution
          </h1>
          <p className="mt-0.5 font-mono text-[11px] uppercase tracking-[0.1em] text-muted-foreground">
            Case 24-071 · AIS Correlation & Scoring · Stage 04
          </p>
        </div>
        <StatusBadge tone="ok" dot>Completed</StatusBadge>
      </div>

      {/* Scoring summary */}
      <section className="rounded-sm border border-border bg-card p-4">
        <SectionLabel>Attribution Scoring Summary</SectionLabel>
        <div className="mt-3 grid grid-cols-2 gap-3 sm:grid-cols-4">
          <div className="rounded-sm border border-border bg-background/60 p-3">
            <div className="font-mono text-[9px] uppercase tracking-[0.1em] text-muted-foreground mb-1">Candidates Evaluated</div>
            <div className="font-mono text-[20px] font-bold text-foreground">{VESSELS.length}</div>
          </div>
          <div className="rounded-sm border border-border bg-background/60 p-3">
            <div className="font-mono text-[9px] uppercase tracking-[0.1em] text-muted-foreground mb-1">Leading Score</div>
            <div className="font-mono text-[20px] font-bold text-saffron">{VESSELS[0].attributionScore}%</div>
          </div>
          <div className="rounded-sm border border-border bg-background/60 p-3">
            <div className="font-mono text-[9px] uppercase tracking-[0.1em] text-muted-foreground mb-1">Method</div>
            <div className="text-[12px] font-medium text-foreground">Spatiotemporal Overlap</div>
          </div>
          <div className="rounded-sm border border-border bg-background/60 p-3">
            <div className="font-mono text-[9px] uppercase tracking-[0.1em] text-muted-foreground mb-1">AIS Coverage</div>
            <div className="font-mono text-[20px] font-bold text-[var(--ok)]">98%</div>
          </div>
        </div>
      </section>

      {/* Candidate Vessels */}
      <div className="mt-3 space-y-3">
        {VESSELS.map((vessel) => {
          const isExpanded = expandedId === vessel.id
          return (
            <section key={vessel.id} className={cn(
              'rounded-sm border bg-card transition-colors',
              vessel.rank === 1 ? 'border-saffron/30' : 'border-border',
            )}>
              <button
                type="button"
                onClick={() => setExpandedId(isExpanded ? null : vessel.id)}
                className="flex w-full items-center gap-3 p-4 text-left"
              >
                <span className={cn(
                  'grid h-8 w-8 shrink-0 place-items-center rounded-sm font-mono text-sm font-bold',
                  vessel.rank === 1 ? 'bg-saffron text-saffron-foreground' : 'bg-muted text-muted-foreground',
                )}>
                  {vessel.rank}
                </span>
                <div className="min-w-0 flex-1">
                  <div className="flex items-center gap-2">
                    <span className="text-[14px] font-semibold text-foreground">{vessel.name}</span>
                    <StatusBadge tone={roleTone(vessel.role)} dot>{vessel.role}</StatusBadge>
                  </div>
                  <div className="mt-0.5 font-mono text-[11px] text-muted-foreground">
                    {vessel.type} · {vessel.flag} · {vessel.imo}
                  </div>
                </div>
                <div className="flex items-center gap-3">
                  <div className="text-right hidden sm:block">
                    <div className="font-mono text-[18px] font-bold text-foreground">{vessel.attributionScore}%</div>
                    <div className="font-mono text-[9px] uppercase tracking-[0.1em] text-muted-foreground">Score</div>
                  </div>
                  <ChevronRight className={cn(
                    'h-4 w-4 text-muted-foreground transition-transform',
                    isExpanded && 'rotate-90',
                  )} />
                </div>
              </button>

              {isExpanded && (
                <div className="border-t border-border px-4 pb-4 pt-3">
                  <div className="grid grid-cols-2 gap-3 sm:grid-cols-4 lg:grid-cols-6">
                    {[
                      { icon: MapPin, label: 'Position', value: `${vessel.position.lat.toFixed(3)}° N, ${vessel.position.lng.toFixed(3)}° E` },
                      { icon: Clock, label: 'Last AIS', value: vessel.lastSeenUtc },
                      { icon: Navigation, label: 'Speed', value: `${vessel.speedKn} kn` },
                      { icon: Navigation, label: 'Heading', value: `${vessel.headingDeg}°` },
                      { icon: Ship, label: 'Flag', value: vessel.flag },
                      { icon: Radio, label: 'Track Points', value: `${vessel.track.length}` },
                    ].map((item) => (
                      <div key={item.label} className="rounded-sm border border-border bg-background/50 p-2.5">
                        <div className="flex items-center gap-1.5 mb-1">
                          <item.icon className="h-3 w-3 text-muted-foreground/60" />
                          <span className="font-mono text-[9px] uppercase tracking-[0.1em] text-muted-foreground">{item.label}</span>
                        </div>
                        <span className="font-mono text-[12px] font-medium text-foreground">{item.value}</span>
                      </div>
                    ))}
                  </div>

                  <div className="mt-3 rounded-sm border border-border bg-background/40 p-3">
                    <div className="flex items-center gap-2 mb-1.5">
                      {vessel.rank === 1 ? (
                        <AlertTriangle className="h-3.5 w-3.5 text-saffron" />
                      ) : (
                        <Check className="h-3.5 w-3.5 text-[var(--ok)]" />
                      )}
                      <span className="font-mono text-[9px] font-semibold uppercase tracking-[0.1em] text-muted-foreground">Analysis Notes</span>
                    </div>
                    <p className="text-[12px] leading-relaxed text-foreground/80">{vessel.notes}</p>
                  </div>

                  {/* Score bar */}
                  <div className="mt-3">
                    <div className="flex items-center justify-between mb-1">
                      <span className="text-[11px] text-muted-foreground">Attribution Score</span>
                      <span className="font-mono text-[12px] font-bold text-foreground">{vessel.attributionScore}%</span>
                    </div>
                    <Meter value={vessel.attributionScore} tone={vessel.rank === 1 ? 'saffron' : 'muted'} />
                  </div>
                </div>
              )}
            </section>
          )
        })}
      </div>

      {/* Scoring methodology */}
      <section className="mt-3 rounded-sm border border-border bg-card p-4">
        <SectionLabel>Scoring Methodology</SectionLabel>
        <div className="mt-3 grid grid-cols-1 gap-2 sm:grid-cols-3">
          {[
            { label: 'Spatial Proximity', description: 'Minimum distance between vessel track and origin field centroid.', weight: '40%' },
            { label: 'Temporal Overlap', description: 'Vessel presence during the estimated release window (± 2 h).', weight: '35%' },
            { label: 'AIS Behavior', description: 'Speed reductions, course changes, transponder gaps near the origin.', weight: '25%' },
          ].map((item) => (
            <div key={item.label} className="rounded-sm border border-border bg-background/50 p-3">
              <div className="flex items-center justify-between mb-1.5">
                <span className="text-[12px] font-semibold text-foreground">{item.label}</span>
                <span className="font-mono text-[10px] font-bold text-saffron">{item.weight}</span>
              </div>
              <p className="text-[11px] leading-snug text-muted-foreground">{item.description}</p>
            </div>
          ))}
        </div>
      </section>
    </>
  )
}
