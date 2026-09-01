'use client'

import { EVIDENCE_HEALTH } from '@/lib/mock-data'
import { Meter } from './primitives'

export function EvidenceHealth() {
  const { overall, metrics } = EVIDENCE_HEALTH
  const r = 26
  const c = 2 * Math.PI * r
  const dash = (overall / 100) * c

  return (
    <div className="flex items-center gap-4">
      {/* Circular gauge */}
      <div className="relative h-[68px] w-[68px] shrink-0">
        <svg viewBox="0 0 64 64" className="h-full w-full -rotate-90">
          <circle
            cx="32"
            cy="32"
            r={r}
            fill="none"
            stroke="var(--muted)"
            strokeWidth="6"
          />
          <circle
            cx="32"
            cy="32"
            r={r}
            fill="none"
            stroke="var(--ok)"
            strokeWidth="6"
            strokeLinecap="round"
            strokeDasharray={`${dash} ${c}`}
          />
        </svg>
        <div className="absolute inset-0 flex flex-col items-center justify-center leading-none">
          <span className="font-mono text-[15px] font-bold tabular-nums text-foreground">
            {overall}%
          </span>
          <span className="mt-0.5 font-mono text-[7px] uppercase tracking-[0.1em] text-muted-foreground">
            Overall
          </span>
        </div>
      </div>

      {/* Breakdown */}
      <div className="min-w-0 flex-1 space-y-1.5">
        {metrics.map((m) => (
          <div key={m.label} className="flex items-center gap-2">
            <span className="w-28 shrink-0 truncate text-[11px] text-muted-foreground">
              {m.label}
            </span>
            <Meter value={m.value} tone="navy" className="flex-1" />
            <span className="w-8 shrink-0 text-right font-mono text-[10px] font-medium tabular-nums text-foreground">
              {m.value}%
            </span>
          </div>
        ))}
      </div>
    </div>
  )
}
