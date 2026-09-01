'use client'

import { PIPELINE, type PipelineStatus } from '@/lib/mock-data'
import { cn } from '@/lib/utils'
import {
  Check,
  ChevronRight,
  CircleDot,
  Crosshair,
  GitCompareArrows,
  Radar,
  ShieldCheck,
  Waypoints,
} from 'lucide-react'
import { useState } from 'react'
import { SectionLabel, StatusBadge } from './primitives'

const STAGE_ICONS = [Radar, GitCompareArrows, Waypoints, Crosshair, ShieldCheck, CircleDot]

function statusTone(s: PipelineStatus): 'ok' | 'warn' {
  return s === 'Pending Approval' ? 'warn' : 'ok'
}

export function AnalyticalPipeline() {
  const [openId, setOpenId] = useState<string | null>(null)
  const open = PIPELINE.find((s) => s.id === openId)

  return (
    <section className="rounded-sm border border-border bg-card p-3.5">
      <div className="mb-3 flex items-center justify-between">
        <SectionLabel>Analytical Pipeline</SectionLabel>
        <span className="font-mono text-[9px] uppercase tracking-[0.1em] text-muted-foreground">
          5 of 6 complete
        </span>
      </div>

      <div className="flex items-stretch gap-1 overflow-x-auto scroll-thin pb-1">
        {PIPELINE.map((stage, i) => {
          const Icon = STAGE_ICONS[i] ?? CircleDot
          const done = stage.status !== 'Pending Approval'
          const isOpen = openId === stage.id
          return (
            <div key={stage.id} className="flex min-w-0 flex-1 items-center">
              <button
                type="button"
                onClick={() => setOpenId(isOpen ? null : stage.id)}
                aria-expanded={isOpen}
                className={cn(
                  'group flex min-w-[120px] flex-1 flex-col gap-1.5 rounded-sm border p-2.5 text-left transition-colors',
                  isOpen
                    ? 'border-primary/40 bg-primary/5'
                    : 'border-border bg-background/40 hover:border-muted-foreground/30 hover:bg-muted/40',
                )}
              >
                <div className="flex items-center justify-between">
                  <span className="font-mono text-[10px] font-semibold text-muted-foreground">
                    {stage.index}
                  </span>
                  <span
                    className={cn(
                      'grid h-5 w-5 place-items-center rounded-full',
                      done
                        ? 'bg-[color-mix(in_oklch,var(--ok)_18%,transparent)] text-[color-mix(in_oklch,var(--ok)_60%,black)]'
                        : 'bg-[color-mix(in_oklch,var(--warn)_20%,transparent)] text-[color-mix(in_oklch,var(--warn)_55%,black)]',
                    )}
                  >
                    {done ? <Check className="h-3 w-3" /> : <Icon className="h-3 w-3" />}
                  </span>
                </div>
                <span className="text-[12px] font-semibold leading-tight text-foreground">
                  {stage.title}
                </span>
                <StatusBadge tone={statusTone(stage.status)} className="w-fit">
                  {stage.status}
                </StatusBadge>
              </button>

              {i < PIPELINE.length - 1 && (
                <ChevronRight className="mx-0.5 h-4 w-4 shrink-0 text-muted-foreground/40" />
              )}
            </div>
          )
        })}
      </div>

      {open && (
        <div className="mt-3 rounded-sm border border-border bg-muted/30 p-3">
          <div className="flex items-center gap-2">
            <span className="font-mono text-[10px] font-semibold text-muted-foreground">
              {open.index}
            </span>
            <span className="text-[13px] font-semibold text-foreground">{open.title}</span>
            <StatusBadge tone={statusTone(open.status)} className="ml-auto">
              {open.status}
            </StatusBadge>
          </div>
          <p className="mt-1.5 text-[12px] leading-relaxed text-muted-foreground">
            {open.detail}
          </p>
          <div className="mt-2.5 grid grid-cols-1 gap-2 sm:grid-cols-3">
            {open.outputs.map((o) => (
              <div key={o.label} className="rounded-sm border border-border bg-card px-2.5 py-1.5">
                <div className="font-mono text-[9px] uppercase tracking-[0.1em] text-muted-foreground">
                  {o.label}
                </div>
                <div className="mt-0.5 font-mono text-[12px] font-medium text-foreground">
                  {o.value}
                </div>
              </div>
            ))}
          </div>
        </div>
      )}
    </section>
  )
}
