'use client'

import { useOperatorCaseData } from '@/lib/operator-case-context'
import { EVIDENCE_HEALTH } from '@/lib/mock-data'
import { Meter } from './primitives'

/** Real components come from OperatorCase.evidence.components (each with a
 * `.score` that is `null`, never 0, when unmeasured — per the backend
 * contract's own EMPTY-BUT-VALID distinction). `null` scores are excluded
 * from the overall average rather than treated as 0, and rendered with a
 * "—" bar rather than a full/empty one, so an unmeasured component never
 * silently drags the score down or up. */
function useEvidenceHealth() {
  const oc = useOperatorCaseData()
  if (!oc) return EVIDENCE_HEALTH

  const measured = oc.evidence.components.filter((c) => c.score !== null)
  const overall =
    measured.length > 0
      ? Math.round((measured.reduce((sum, c) => sum + (c.score ?? 0), 0) / measured.length) * 100)
      : 0

  return {
    overall,
    metrics: oc.evidence.components.map((c) => ({
      label: c.component,
      value: c.score !== null ? Math.round(c.score * 100) : null,
      reason: c.reason,
    })),
  }
}

export function EvidenceHealth() {
  const { overall, metrics } = useEvidenceHealth()
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
          <span className="font-mono text-[16px] font-bold tabular-nums text-foreground">
            {overall}%
          </span>
          <span className="mt-0.5 font-mono text-[8px] uppercase tracking-[0.1em] text-muted-foreground">
            Overall
          </span>
        </div>
      </div>

      {/* Breakdown */}
      <div className="min-w-0 flex-1 space-y-1.5">
        {metrics.map((m) => (
          <div key={m.label} className="flex items-center gap-2" title={'reason' in m ? m.reason ?? undefined : undefined}>
            <span className="w-28 shrink-0 truncate text-[12px] text-muted-foreground">
              {m.label}
            </span>
            <Meter value={m.value ?? 0} tone={m.value === null ? 'muted' : 'navy'} className="flex-1" />
            <span className="w-8 shrink-0 text-right font-mono text-[11px] font-medium tabular-nums text-foreground">
              {m.value !== null ? `${m.value}%` : '—'}
            </span>
          </div>
        ))}
      </div>
    </div>
  )
}
