'use client'

import { CURRENT_MISSION_STATE, MISSION_STATES } from '@/lib/mock-data'
import { SectionLabel, StatusBadge } from '@/components/primitives'
import { Radar, Check, Clock, MapPin, Plane, Ship, Target, ShieldCheck } from 'lucide-react'
import { cn } from '@/lib/utils'

const MISSIONS = [
  { id: 'MSN-071-A', case: 'CASE 24-071', type: 'Inspection / Overflight', asset: 'Aircraft-02', target: 'MT Samudra Prakash', region: 'Arabian Sea', window: '10:30–11:15 UTC', status: 'PENDING AUTH' as const, priority: 'HIGH' },
  { id: 'MSN-071-B', case: 'CASE 24-071', type: 'Monitoring', asset: 'Patrol Vessel-03', target: 'MV Western Kaveri', region: 'Arabian Sea', window: '10:45–12:00 UTC', status: 'PENDING AUTH' as const, priority: 'MEDIUM' },
  { id: 'MSN-070-A', case: 'CASE 24-070', type: 'Sampling', asset: 'Patrol Vessel-01', target: 'Oil slick', region: 'Gulf of Kutch', window: '08:00–09:30 UTC', status: 'IN PROGRESS' as const, priority: 'HIGH' },
]

const MISSION_HISTORY = [
  { id: 'MSN-068-A', case: 'CASE 24-068', type: 'Interception', asset: 'Patrol Vessel-05', outcome: 'Vessel boarded — no violations found', date: '28 JUN 2024', status: 'COMPLETED' },
  { id: 'MSN-067-A', case: 'CASE 24-067', type: 'Overflight', asset: 'Aircraft-01', outcome: 'Oil slick photographed — evidence collected', date: '25 JUN 2024', status: 'COMPLETED' },
  { id: 'MSN-066-A', case: 'CASE 24-066', type: 'Monitoring', asset: 'Patrol Vessel-02', outcome: 'Vessel departed EEZ — no action required', date: '22 JUN 2024', status: 'COMPLETED' },
]

function statusTone(status: string) {
  if (status === 'IN PROGRESS') return 'ok' as const
  if (status === 'PENDING AUTH') return 'warn' as const
  if (status === 'COMPLETED') return 'muted' as const
  return 'muted' as const
}

export default function MissionsPage() {
  const currentIdx = MISSION_STATES.indexOf(CURRENT_MISSION_STATE)

  return (
    <>
      <div className="mb-3 flex flex-wrap items-end justify-between gap-2">
        <div>
          <h1 className="text-balance text-lg font-semibold leading-tight tracking-tight text-foreground sm:text-xl">
            Mission Control
          </h1>
          <p className="mt-0.5 font-mono text-[11px] uppercase tracking-[0.1em] text-muted-foreground">
            Active & planned missions · Maritime Intelligence System
          </p>
        </div>
      </div>

      {/* Mission pipeline */}
      <section className="rounded-sm border border-border bg-card p-4">
        <SectionLabel>Current Mission Pipeline — CASE 24-071</SectionLabel>
        <ol className="mt-3 flex items-center gap-1 overflow-x-auto scroll-thin pb-1">
          {MISSION_STATES.map((state, i) => {
            const done = i < currentIdx
            const current = i === currentIdx
            return (
              <li key={state} className="flex flex-1 items-center gap-1">
                <div className={cn(
                  'flex min-w-[92px] flex-1 items-center gap-2 rounded-sm border px-2.5 py-2',
                  current ? 'border-[color-mix(in_oklch,var(--warn)_45%,transparent)] bg-[color-mix(in_oklch,var(--warn)_12%,transparent)]' :
                  done ? 'border-[color-mix(in_oklch,var(--ok)_35%,transparent)] bg-[color-mix(in_oklch,var(--ok)_8%,transparent)]' :
                  'border-border bg-background/40',
                )}>
                  <span className={cn(
                    'grid h-4 w-4 shrink-0 place-items-center rounded-full font-mono text-[9px] font-bold',
                    current ? 'bg-[var(--warn)] text-[oklch(0.22_0.03_60)]' :
                    done ? 'bg-[var(--ok)] text-primary-foreground' :
                    'bg-muted text-muted-foreground',
                  )}>
                    {done ? <Check className="h-2.5 w-2.5" /> : i + 1}
                  </span>
                  <span className={cn(
                    'truncate font-mono text-[10px] font-semibold uppercase tracking-[0.06em]',
                    current ? 'text-[color-mix(in_oklch,var(--warn)_55%,black)]' :
                    done ? 'text-[color-mix(in_oklch,var(--ok)_55%,black)]' :
                    'text-muted-foreground',
                  )}>
                    {state}
                  </span>
                </div>
                {i < MISSION_STATES.length - 1 && (
                  <span className={cn('h-px w-2 shrink-0', done ? 'bg-[var(--ok)]' : 'bg-border')} aria-hidden="true" />
                )}
              </li>
            )
          })}
        </ol>
      </section>

      {/* Active missions */}
      <section className="mt-3 rounded-sm border border-border bg-card p-4">
        <SectionLabel>Active & Pending Missions</SectionLabel>
        <div className="mt-3 space-y-3">
          {MISSIONS.map((m) => (
            <div key={m.id} className="rounded-sm border border-border bg-background/50 p-4">
              <div className="flex items-start justify-between gap-2">
                <div className="flex items-center gap-2">
                  {m.asset.startsWith('Aircraft') ? <Plane className="h-4 w-4 text-saffron" /> : <Ship className="h-4 w-4 text-teal" />}
                  <span className="text-[13px] font-semibold text-foreground">{m.id}</span>
                  <StatusBadge tone={statusTone(m.status)} dot>{m.status}</StatusBadge>
                  <StatusBadge tone={m.priority === 'HIGH' ? 'warn' : 'muted'}>{m.priority}</StatusBadge>
                </div>
                <span className="font-mono text-[10px] text-muted-foreground">{m.case}</span>
              </div>
              <div className="mt-2 grid grid-cols-2 gap-2 sm:grid-cols-4">
                <div><div className="font-mono text-[9px] uppercase tracking-[0.1em] text-muted-foreground">Asset</div><div className="text-[12px] font-medium text-foreground">{m.asset}</div></div>
                <div><div className="font-mono text-[9px] uppercase tracking-[0.1em] text-muted-foreground">Target</div><div className="text-[12px] font-medium text-foreground">{m.target}</div></div>
                <div><div className="font-mono text-[9px] uppercase tracking-[0.1em] text-muted-foreground">Task</div><div className="text-[12px] font-medium text-foreground">{m.type}</div></div>
                <div><div className="font-mono text-[9px] uppercase tracking-[0.1em] text-muted-foreground">Window</div><div className="font-mono text-[12px] font-medium text-foreground">{m.window}</div></div>
              </div>
            </div>
          ))}
        </div>
      </section>

      {/* Mission history */}
      <section className="mt-3 rounded-sm border border-border bg-card p-4">
        <SectionLabel>Mission History</SectionLabel>
        <div className="mt-3 overflow-x-auto">
          <table className="w-full text-left">
            <thead>
              <tr className="border-b border-border">
                {['Mission ID', 'Case', 'Type', 'Asset', 'Outcome', 'Date', 'Status'].map((h) => (
                  <th key={h} className="pb-2 pr-4 font-mono text-[9px] font-semibold uppercase tracking-[0.12em] text-muted-foreground whitespace-nowrap">{h}</th>
                ))}
              </tr>
            </thead>
            <tbody>
              {MISSION_HISTORY.map((m) => (
                <tr key={m.id} className="border-b border-border/50 last:border-b-0">
                  <td className="py-2.5 pr-4 font-mono text-[11px] font-medium text-foreground">{m.id}</td>
                  <td className="py-2.5 pr-4 font-mono text-[11px] text-muted-foreground">{m.case}</td>
                  <td className="py-2.5 pr-4 text-[12px] text-foreground">{m.type}</td>
                  <td className="py-2.5 pr-4 text-[12px] text-muted-foreground">{m.asset}</td>
                  <td className="py-2.5 pr-4 text-[12px] text-muted-foreground">{m.outcome}</td>
                  <td className="py-2.5 pr-4 font-mono text-[11px] text-muted-foreground">{m.date}</td>
                  <td className="py-2.5"><StatusBadge tone="ok">Completed</StatusBadge></td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </section>
    </>
  )
}
