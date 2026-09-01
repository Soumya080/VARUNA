'use client'

import { CASE_SUMMARY } from '@/lib/mock-data'
import { cn } from '@/lib/utils'

const toneText: Record<string, string> = {
  ok: 'text-[color-mix(in_oklch,var(--ok)_60%,black)]',
  warn: 'text-[color-mix(in_oklch,var(--warn)_55%,black)]',
  saffron: 'text-[color-mix(in_oklch,var(--saffron)_52%,black)]',
  default: 'text-foreground',
}

export function CaseSummary() {
  return (
    <section aria-label="Case summary" className="grid grid-cols-2 gap-2 sm:grid-cols-3 lg:grid-cols-5">
      {CASE_SUMMARY.map((m) => (
        <div
          key={m.label}
          className="rounded-sm border border-border bg-card px-3 py-2.5"
        >
          <div className="font-mono text-[9px] font-medium uppercase tracking-[0.12em] text-muted-foreground">
            {m.label}
          </div>
          <div
            className={cn(
              'mt-1 font-mono text-[15px] font-semibold leading-none tabular-nums',
              toneText[m.tone ?? 'default'],
            )}
          >
            {m.primary}
          </div>
          {m.secondary && (
            <div className="mt-1 text-[10px] leading-none text-muted-foreground">
              {m.secondary}
            </div>
          )}
        </div>
      ))}
    </section>
  )
}
