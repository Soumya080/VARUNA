'use client'

import { ASSIGNMENTS, FEASIBILITY } from '@/lib/mock-data'
import { SectionLabel, StatusBadge, Meter } from '@/components/primitives'
import { ShieldCheck, Plane, Ship, Clock, Target, Check, X, AlertTriangle } from 'lucide-react'
import { cn } from '@/lib/utils'

export default function AssignmentMissionPage() {
  return (
    <>
      <div className="mb-3 flex flex-wrap items-end justify-between gap-2">
        <div>
          <h1 className="text-balance text-lg font-semibold leading-tight tracking-tight text-foreground sm:text-xl">
            Assignment &amp; Mission Planning
          </h1>
          <p className="mt-0.5 font-mono text-[11px] uppercase tracking-[0.1em] text-muted-foreground">
            Case 24-071 · Asset Allocation & Authorization · Stage 06
          </p>
        </div>
        <StatusBadge tone="warn" dot>Pending Approval</StatusBadge>
      </div>

      {/* Assignments */}
      <section className="rounded-sm border border-border bg-card p-4">
        <SectionLabel>Assignment Table</SectionLabel>
        <div className="mt-3 overflow-x-auto">
          <table className="w-full text-left">
            <thead>
              <tr className="border-b border-border">
                {['ID', 'Candidate', 'Recommendation', 'Asset', 'Task', 'Priority', 'Window', 'Status'].map((h) => (
                  <th key={h} className="pb-2 pr-4 font-mono text-[9px] font-semibold uppercase tracking-[0.12em] text-muted-foreground whitespace-nowrap">{h}</th>
                ))}
              </tr>
            </thead>
            <tbody>
              {ASSIGNMENTS.map((a) => (
                <tr key={a.id} className="border-b border-border/50 last:border-b-0">
                  <td className="py-2.5 pr-4 font-mono text-[11px] font-medium text-muted-foreground">{a.id.toUpperCase()}</td>
                  <td className="py-2.5 pr-4 text-[12px] font-semibold text-foreground">{a.candidate}</td>
                  <td className="py-2.5 pr-4">
                    <StatusBadge tone={a.recommendation === 'PRIMARY LEAD' ? 'saffron' : 'muted'} dot>{a.recommendation}</StatusBadge>
                  </td>
                  <td className="py-2.5 pr-4 font-mono text-[12px] text-foreground">{a.asset}</td>
                  <td className="py-2.5 pr-4 text-[12px] text-foreground">{a.task}</td>
                  <td className="py-2.5 pr-4">
                    <StatusBadge tone={a.priority === 'HIGH' ? 'warn' : 'muted'}>{a.priority}</StatusBadge>
                  </td>
                  <td className="py-2.5 pr-4 font-mono text-[12px] text-foreground whitespace-nowrap">{a.window}</td>
                  <td className="py-2.5">
                    <StatusBadge tone="warn" dot>{a.status}</StatusBadge>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </section>

      {/* Feasibility + Authorization */}
      <div className="mt-3 grid grid-cols-1 gap-3 lg:grid-cols-2">
        {/* Feasibility */}
        <section className="rounded-sm border border-border bg-card p-4">
          <div className="mb-3 flex items-center gap-2">
            <Check className="h-4 w-4 text-[var(--ok)]" />
            <SectionLabel>Feasibility Assessment</SectionLabel>
          </div>
          <div className="space-y-2">
            {FEASIBILITY.map((item) => (
              <div key={item.label} className="flex items-center justify-between py-1.5 border-b border-border/50 last:border-b-0">
                <span className="text-[12px] text-muted-foreground">{item.label}</span>
                <div className="flex items-center gap-2">
                  <span className="font-mono text-[12px] font-medium text-foreground">{item.value}</span>
                  {item.feasible ? (
                    <span className="grid h-5 w-5 place-items-center rounded-full bg-[color-mix(in_oklch,var(--ok)_18%,transparent)]">
                      <Check className="h-3 w-3 text-[var(--ok)]" />
                    </span>
                  ) : (
                    <span className="grid h-5 w-5 place-items-center rounded-full bg-[color-mix(in_oklch,var(--destructive)_18%,transparent)]">
                      <X className="h-3 w-3 text-destructive" />
                    </span>
                  )}
                </div>
              </div>
            ))}
          </div>
          <div className="mt-3 rounded-sm border border-[color-mix(in_oklch,var(--ok)_35%,transparent)] bg-[color-mix(in_oklch,var(--ok)_8%,transparent)] p-3">
            <div className="flex items-center gap-2">
              <Check className="h-4 w-4 text-[var(--ok)]" />
              <span className="font-mono text-[11px] font-semibold uppercase tracking-[0.08em] text-[color-mix(in_oklch,var(--ok)_60%,black)]">
                All feasibility checks passed
              </span>
            </div>
          </div>
        </section>

        {/* Authorization */}
        <section className="rounded-sm border border-border bg-card p-4">
          <div className="mb-3 flex items-center gap-2">
            <ShieldCheck className="h-4 w-4 text-saffron" />
            <SectionLabel>Authorization Workflow</SectionLabel>
          </div>
          <div className="space-y-3">
            {[
              { step: 'Evidence reviewed', by: 'Analyst Rao', time: '06:52 UTC', done: true },
              { step: 'Feasibility confirmed', by: 'System (automated)', time: '06:53 UTC', done: true },
              { step: 'Mission plan generated', by: 'System (automated)', time: '06:53 UTC', done: true },
              { step: 'Authorization requested', by: 'Analyst Rao', time: '06:55 UTC', done: true },
              { step: 'Commanding Officer review', by: 'Pending · CO Watch', time: '—', done: false },
              { step: 'Dispatch order', by: 'Pending', time: '—', done: false },
            ].map((item, i) => (
              <div key={i} className="flex items-start gap-3">
                <span className={cn(
                  'mt-0.5 grid h-5 w-5 shrink-0 place-items-center rounded-full font-mono text-[9px] font-bold',
                  item.done ? 'bg-[var(--ok)] text-white' : 'bg-muted text-muted-foreground',
                )}>
                  {item.done ? <Check className="h-3 w-3" /> : i + 1}
                </span>
                <div className="flex-1">
                  <div className="text-[12px] font-medium text-foreground">{item.step}</div>
                  <div className="flex items-center gap-2 mt-0.5">
                    <span className="text-[11px] text-muted-foreground">{item.by}</span>
                    <span className="font-mono text-[10px] text-muted-foreground">{item.time}</span>
                  </div>
                </div>
              </div>
            ))}
          </div>

          <div className="mt-4 flex gap-2">
            <button type="button" className="flex flex-1 items-center justify-center gap-1.5 rounded-sm bg-primary px-4 py-2.5 text-[12px] font-semibold uppercase tracking-[0.08em] text-primary-foreground transition-colors hover:bg-[var(--navy-muted)]">
              <ShieldCheck className="h-4 w-4" />
              Request Authorization
            </button>
          </div>
        </section>
      </div>

      {/* Asset details */}
      <section className="mt-3 rounded-sm border border-border bg-card p-4">
        <SectionLabel>Assigned Assets</SectionLabel>
        <div className="mt-3 grid grid-cols-1 gap-3 sm:grid-cols-2">
          <div className="rounded-sm border border-saffron/20 bg-saffron/5 p-4">
            <div className="flex items-center gap-2 mb-3">
              <Plane className="h-5 w-5 text-saffron" />
              <span className="text-[14px] font-semibold text-foreground">Aircraft-02</span>
              <StatusBadge tone="ok">Available</StatusBadge>
            </div>
            <div className="space-y-1">
              <div className="flex justify-between text-[12px]"><span className="text-muted-foreground">Type</span><span className="font-medium text-foreground">Dornier 228</span></div>
              <div className="flex justify-between text-[12px]"><span className="text-muted-foreground">Task</span><span className="font-medium text-foreground">Inspection / Overflight</span></div>
              <div className="flex justify-between text-[12px]"><span className="text-muted-foreground">Window</span><span className="font-mono font-medium text-foreground">10:30–11:15 UTC</span></div>
              <div className="flex justify-between text-[12px]"><span className="text-muted-foreground">Base</span><span className="font-medium text-foreground">INS Hansa, Goa</span></div>
            </div>
          </div>
          <div className="rounded-sm border border-border bg-background/50 p-4">
            <div className="flex items-center gap-2 mb-3">
              <Ship className="h-5 w-5 text-teal" />
              <span className="text-[14px] font-semibold text-foreground">Patrol Vessel-03</span>
              <StatusBadge tone="ok">Available</StatusBadge>
            </div>
            <div className="space-y-1">
              <div className="flex justify-between text-[12px]"><span className="text-muted-foreground">Type</span><span className="font-medium text-foreground">Interceptor Boat</span></div>
              <div className="flex justify-between text-[12px]"><span className="text-muted-foreground">Task</span><span className="font-medium text-foreground">Monitoring</span></div>
              <div className="flex justify-between text-[12px]"><span className="text-muted-foreground">Window</span><span className="font-mono font-medium text-foreground">10:45–12:00 UTC</span></div>
              <div className="flex justify-between text-[12px]"><span className="text-muted-foreground">Base</span><span className="font-medium text-foreground">Mumbai Harbor</span></div>
            </div>
          </div>
        </div>
      </section>
    </>
  )
}
