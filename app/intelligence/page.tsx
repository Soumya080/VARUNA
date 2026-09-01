'use client'

import { VESSELS } from '@/lib/mock-data'
import { SectionLabel, StatusBadge } from '@/components/primitives'
import { Globe, Radio, Ship, Users, FileSearch, Clock, MapPin, AlertTriangle, TrendingUp, Eye } from 'lucide-react'
import { cn } from '@/lib/utils'

const INTEL_FEED = [
  { id: 'INT-4821', time: '06:50 UTC', source: 'MIS Pipeline', category: 'Detection', title: 'New oil slick detected — Arabian Sea', priority: 'High', detail: 'SAR classification confidence 0.91. Case 24-071 auto-generated.' },
  { id: 'INT-4820', time: '06:12 UTC', source: 'AIS Monitor', category: 'AIS Anomaly', title: 'Transponder gap — MT Samudra Prakash', priority: 'High', detail: '41-minute AIS gap at 18.93° N, 72.78° E. Flagged for correlation.' },
  { id: 'INT-4819', time: '05:30 UTC', source: 'VTMS Mumbai', category: 'EEZ Alert', title: 'Unidentified vessel approaching EEZ boundary', priority: 'Medium', detail: 'Heading 340° at 14 kn toward territorial waters. No response to radio hail.' },
  { id: 'INT-4818', time: '04:00 UTC', source: 'DG Shipping', category: 'Regulatory', title: 'MARPOL inspection notice — Mumbai anchorage', priority: 'Low', detail: 'Scheduled port state control inspection for 3 vessels at Mumbai anchorage.' },
  { id: 'INT-4817', time: '02:15 UTC', source: 'OSINT', category: 'Open Source', title: 'Media report — pollution sighting off Ratnagiri', priority: 'Medium', detail: 'Local fishermen report oily sheen 8 km offshore. Requires SAR confirmation.' },
  { id: 'INT-4816', time: '00:30 UTC', source: 'Partner Agency', category: 'Collaboration', title: 'Sri Lanka Navy — shared AIS data for Bay of Bengal', priority: 'Low', detail: 'Bilateral data sharing agreement — 48-hour AIS history received.' },
]

const VESSEL_PROFILES = VESSELS.map(v => ({
  ...v,
  riskLevel: v.rank === 1 ? 'High' : v.rank === 2 ? 'Medium' : 'Low',
  incidents: v.rank === 1 ? 3 : v.rank === 2 ? 1 : 0,
  watchlisted: v.rank === 1,
}))

const PATTERNS = [
  { label: 'Nighttime AIS gaps in shipping lanes', count: 7, trend: '+2 vs. last month', risk: 'Medium' },
  { label: 'Repeated slow-speed transits near origin fields', count: 4, trend: '+1 vs. last month', risk: 'High' },
  { label: 'Vessel flag-hopping (3+ flag changes in 12 months)', count: 2, trend: 'Stable', risk: 'High' },
  { label: 'Port evasion — vessels avoiding inspection anchorages', count: 3, trend: '-1 vs. last month', risk: 'Medium' },
]

function priorityTone(p: string) {
  if (p === 'High') return 'destructive' as const
  if (p === 'Medium') return 'warn' as const
  return 'muted' as const
}

export default function IntelligencePage() {
  return (
    <>
      <div className="mb-3 flex flex-wrap items-end justify-between gap-2">
        <div>
          <h1 className="text-balance text-lg font-semibold leading-tight tracking-tight text-foreground sm:text-xl">
            Intelligence Fusion Center
          </h1>
          <p className="mt-0.5 font-mono text-[11px] uppercase tracking-[0.1em] text-muted-foreground">
            Multi-source intelligence · 23 feeds active
          </p>
        </div>
        <div className="flex items-center gap-1.5 rounded-sm border border-[color-mix(in_oklch,var(--ok)_45%,transparent)] bg-[color-mix(in_oklch,var(--ok)_16%,transparent)] px-2 py-1">
          <span className="relative flex h-2 w-2">
            <span className="absolute inline-flex h-full w-full rounded-full bg-[var(--ok)] opacity-60 animate-pulse-ring" />
            <span className="relative inline-flex h-2 w-2 rounded-full bg-[var(--ok)]" />
          </span>
          <span className="font-mono text-[10px] font-semibold uppercase tracking-[0.1em] text-[color-mix(in_oklch,var(--ok)_75%,white)]">Live Feed</span>
        </div>
      </div>

      {/* Stats */}
      <div className="grid grid-cols-2 gap-3 sm:grid-cols-4">
        <div className="rounded-sm border border-border bg-card p-3">
          <div className="flex items-center gap-2"><Radio className="h-4 w-4 text-[var(--ok)]" /><span className="font-mono text-[9px] uppercase tracking-[0.12em] text-muted-foreground">Intel Sources</span></div>
          <div className="mt-1 font-mono text-[22px] font-bold text-foreground">23</div>
        </div>
        <div className="rounded-sm border border-border bg-card p-3">
          <div className="flex items-center gap-2"><Eye className="h-4 w-4 text-saffron" /><span className="font-mono text-[9px] uppercase tracking-[0.12em] text-muted-foreground">Watchlisted Vessels</span></div>
          <div className="mt-1 font-mono text-[22px] font-bold text-foreground">{VESSEL_PROFILES.filter(v => v.watchlisted).length}</div>
        </div>
        <div className="rounded-sm border border-border bg-card p-3">
          <div className="flex items-center gap-2"><TrendingUp className="h-4 w-4 text-[var(--warn)]" /><span className="font-mono text-[9px] uppercase tracking-[0.12em] text-muted-foreground">Patterns Detected</span></div>
          <div className="mt-1 font-mono text-[22px] font-bold text-foreground">{PATTERNS.length}</div>
        </div>
        <div className="rounded-sm border border-border bg-card p-3">
          <div className="flex items-center gap-2"><Users className="h-4 w-4 text-teal" /><span className="font-mono text-[9px] uppercase tracking-[0.12em] text-muted-foreground">Partner Agencies</span></div>
          <div className="mt-1 font-mono text-[22px] font-bold text-foreground">5</div>
        </div>
      </div>

      {/* Intelligence feed */}
      <section className="mt-3 rounded-sm border border-border bg-card p-4">
        <div className="flex items-center gap-2 mb-3">
          <Globe className="h-4 w-4 text-teal" />
          <SectionLabel>Intelligence Feed</SectionLabel>
        </div>
        <div className="space-y-2">
          {INTEL_FEED.map(item => (
            <div key={item.id} className="rounded-sm border border-border bg-background/50 p-3 transition-colors hover:bg-muted/30">
              <div className="flex items-start justify-between gap-2">
                <div className="flex items-center gap-2 flex-wrap">
                  <span className="text-[13px] font-semibold text-foreground">{item.title}</span>
                  <StatusBadge tone={priorityTone(item.priority)}>{item.priority}</StatusBadge>
                  <span className="rounded-sm bg-muted px-1.5 py-0.5 font-mono text-[9px] text-muted-foreground">{item.category}</span>
                </div>
              </div>
              <p className="mt-1 text-[12px] text-muted-foreground">{item.detail}</p>
              <div className="mt-2 flex items-center gap-4 text-[11px] text-muted-foreground">
                <span className="flex items-center gap-1"><Clock className="h-3 w-3" />{item.time}</span>
                <span className="flex items-center gap-1"><Radio className="h-3 w-3" />{item.source}</span>
                <span className="font-mono text-[10px]">{item.id}</span>
              </div>
            </div>
          ))}
        </div>
      </section>

      {/* Patterns + Vessel profiles */}
      <div className="mt-3 grid grid-cols-1 gap-3 lg:grid-cols-2">
        <section className="rounded-sm border border-border bg-card p-4">
          <div className="flex items-center gap-2 mb-3">
            <TrendingUp className="h-4 w-4 text-[var(--warn)]" />
            <SectionLabel>Pattern Analysis</SectionLabel>
          </div>
          <div className="space-y-2">
            {PATTERNS.map(p => (
              <div key={p.label} className="rounded-sm border border-border bg-background/50 p-3">
                <div className="flex items-center justify-between gap-2">
                  <span className="text-[12px] font-medium text-foreground">{p.label}</span>
                  <StatusBadge tone={p.risk === 'High' ? 'destructive' : 'warn'}>{p.risk}</StatusBadge>
                </div>
                <div className="mt-1 flex items-center gap-4 text-[11px] text-muted-foreground">
                  <span>{p.count} occurrences</span>
                  <span>{p.trend}</span>
                </div>
              </div>
            ))}
          </div>
        </section>

        <section className="rounded-sm border border-border bg-card p-4">
          <div className="flex items-center gap-2 mb-3">
            <Ship className="h-4 w-4 text-saffron" />
            <SectionLabel>Vessel Profiles</SectionLabel>
          </div>
          <div className="space-y-2">
            {VESSEL_PROFILES.map(v => (
              <div key={v.id} className={cn('rounded-sm border p-3', v.watchlisted ? 'border-saffron/30 bg-saffron/5' : 'border-border bg-background/50')}>
                <div className="flex items-center justify-between gap-2">
                  <div>
                    <div className="flex items-center gap-2">
                      <span className="text-[12px] font-semibold text-foreground">{v.name}</span>
                      {v.watchlisted && <span className="font-mono text-[9px] font-bold text-saffron">★ WATCHLISTED</span>}
                    </div>
                    <div className="text-[11px] text-muted-foreground">{v.type} · {v.flag} · {v.imo}</div>
                  </div>
                  <StatusBadge tone={v.riskLevel === 'High' ? 'destructive' : v.riskLevel === 'Medium' ? 'warn' : 'ok'}>{v.riskLevel} Risk</StatusBadge>
                </div>
                <div className="mt-1 text-[11px] text-muted-foreground">{v.incidents} prior incident{v.incidents !== 1 ? 's' : ''} on record</div>
              </div>
            ))}
          </div>
        </section>
      </div>
    </>
  )
}
