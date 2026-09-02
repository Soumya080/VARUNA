'use client'

import { FEASIBILITY } from '@/lib/mock-data'
import { Check } from 'lucide-react'
import { SectionLabel } from './primitives'

export function FeasibilitySummary() {
  return (
    <section className="rounded-sm border border-border bg-card p-3.5">
      <div className="mb-3 flex items-center justify-between">
        <SectionLabel>Feasibility Summary</SectionLabel>
        <span className="font-mono text-[10px] uppercase tracking-[0.1em] text-[color-mix(in_oklch,var(--ok)_55%,black)]">
          All checks passed
        </span>
      </div>
      <ul className="divide-y divide-border overflow-hidden rounded-sm border border-border">
        {FEASIBILITY.map((f) => (
          <li
            key={f.label}
            className="flex items-center justify-between gap-3 bg-background/40 px-3 py-2"
          >
            <div className="flex items-center gap-2">
              <span className="grid h-4 w-4 shrink-0 place-items-center rounded-full bg-[color-mix(in_oklch,var(--ok)_20%,transparent)]">
                <Check className="h-2.5 w-2.5 text-[color-mix(in_oklch,var(--ok)_60%,black)]" />
              </span>
              <span className="font-mono text-[11px] uppercase tracking-[0.08em] text-muted-foreground">
                {f.label}
              </span>
            </div>
            <span className="text-right text-[13px] font-semibold text-foreground">{f.value}</span>
          </li>
        ))}
      </ul>
    </section>
  )
}
