'use client'

/**
 * Cockpit sub-panels. Every value is read from the canonical OperatorCase.
 * This file imports NOTHING from lib/mock-data.
 */
import { InfoTip, StatusBadge } from '@/components/primitives'
import { EvidenceModeBadge } from '@/components/evidence-mode-badge'
import type { OperatorCase, SectionEnvelope } from '@/lib/operator-case-types'
import type { StageEvent } from '@/lib/use-run-stream'
import type { DerivedStageState } from '@/lib/stage-state'
import { STAGE_LABEL as CANONICAL_STAGE_LABEL } from '@/lib/stages'
import { cn } from '@/lib/utils'
import type { ReactNode } from 'react'

export function Card({
  title,
  right,
  children,
  id,
}: {
  title: string
  right?: ReactNode
  children: ReactNode
  id?: string
}) {
  return (
    <section id={id} className="scroll-mt-16 rounded-sm border border-border bg-card">
      <div className="flex items-center justify-between gap-2 border-b border-border bg-muted/40 px-3 py-2">
        <h3 className="font-mono text-[11px] font-semibold uppercase tracking-[0.13em] text-foreground">
          {title}
        </h3>
        {right}
      </div>
      <div className="px-3 py-2.5">{children}</div>
    </section>
  )
}

export function Row({ label, value }: { label: string; value: ReactNode }) {
  return (
    <div className="flex items-baseline justify-between gap-3 py-[3px]">
      <span className="shrink-0 text-[12px] text-muted-foreground">{label}</span>
      <span className="text-right font-mono text-[12px] font-medium tabular-nums text-foreground">
        {value}
      </span>
    </div>
  )
}

/** Honest status chip driven by the section's real ProducerStatus. */
export function SectionStatus({ s }: { s: SectionEnvelope<unknown> | undefined }) {
  if (!s) return <StatusBadge tone="muted">absent</StatusBadge>
  const tone =
    s.status === 'produced' ? 'ok' : s.status === 'blocked' ? 'destructive' : 'muted'
  return (
    <div className="flex items-center gap-1.5">
      <StatusBadge tone={tone}>{s.status.replace(/_/g, ' ')}</StatusBadge>
      {s.evidence_mode && <EvidenceModeBadge mode={s.evidence_mode} compact />}
    </div>
  )
}

/* ------------------------------- Timeline ------------------------------- */

/**
 * Phase 7 fix (docs/product/HONESTY_LEDGER.md #23): this used to take raw
 * `stageOrder`/`events` from `useRunStream()` directly, which are `[]`/`{}`
 * on fresh page load — before any live SSE run has happened — so all 13
 * stages rendered as grey "pending" placeholders even when the composed
 * `OperatorCase` already showed every stage had genuinely run. Now takes
 * the already-derived `DerivedStageState[]` from `lib/stage-state.ts`,
 * which falls back to `oc`'s own section statuses when no live event
 * exists yet — `source: 'composed'` stages render as done, just without a
 * live timing number (composed status is not itself a live measurement).
 */
export function RunTimeline({ stages }: { stages: DerivedStageState[] }) {
  return (
    <ol className="space-y-1">
      {stages.map((s, i) => {
        const done = s.status === 'produced'
        const bad = s.status === 'blocked' || s.status === 'error'
        const pending = s.source === 'none'
        return (
          <li
            key={s.stage}
            className={cn(
              'flex items-center gap-2 rounded-sm border px-2 py-1.5',
              done && 'border-[color-mix(in_oklch,var(--ok)_35%,transparent)] bg-[color-mix(in_oklch,var(--ok)_8%,transparent)]',
              bad && 'border-[color-mix(in_oklch,var(--destructive)_40%,transparent)] bg-[color-mix(in_oklch,var(--destructive)_8%,transparent)]',
              !done && !bad && !pending && 'border-border bg-muted/30',
              pending && 'border-border bg-background/40 opacity-60',
            )}
            title={s.reason ?? undefined}
          >
            <span
              className={cn(
                'grid h-4 w-4 shrink-0 place-items-center rounded-full font-mono text-[9px] font-bold',
                done && 'bg-[var(--ok)] text-primary-foreground',
                bad && 'bg-destructive text-white',
                !done && !bad && 'bg-muted text-muted-foreground',
              )}
            >
              {done ? '✓' : bad ? '!' : i + 1}
            </span>
            <span className="min-w-0 flex-1 truncate text-[12px] text-foreground">
              {CANONICAL_STAGE_LABEL[s.stage] ?? s.stage}
            </span>
            {s.source === 'live' && s.elapsedMs != null ? (
              <span className="shrink-0 font-mono text-[10px] tabular-nums text-muted-foreground">
                {done ? `${s.elapsedMs.toFixed(0)}ms` : s.status.replace(/_/g, ' ')}
              </span>
            ) : s.source === 'composed' ? (
              <span
                className="shrink-0 font-mono text-[9px] uppercase tracking-[0.06em] text-muted-foreground"
                title="From the already-composed case, not a live measurement this page load"
              >
                {done ? 'already done' : s.status.replace(/_/g, ' ')}
              </span>
            ) : (
              <span className="shrink-0 font-mono text-[10px] text-muted-foreground">—</span>
            )}
          </li>
        )
      })}
    </ol>
  )
}

/* ------------------------------- Evidence ------------------------------- */

export function EvidencePanels({ oc }: { oc: OperatorCase }) {
  const det = oc.detection
  const intel = oc.intelligence
  const hyps = intel.hypotheses?.hypotheses ?? []
  const top = hyps.length
    ? hyps.slice().sort((a, b) => b.posterior - a.posterior)[0]
    : null
  const unc = intel.uncertainty
  const attr = oc.attribution
  const val = oc.validity

  return (
    <div className="space-y-2">
      <Card title="NETRA — Detection" right={<SectionStatus s={det} />}>
        {det.status === 'produced' && det.value ? (
          <>
            <Row label="Classification" value={det.value.classification ?? '—'} />
            <Row label="Confidence" value={det.value.confidence?.toFixed?.(2) ?? '—'} />
            <Row label="Area" value={det.value.area_km2 != null ? `${det.value.area_km2} km²` : '—'} />
            <Row label="Model" value={det.value.netra_model_version ?? '—'} />
          </>
        ) : (
          <p className="text-[12px] text-muted-foreground">{det.reason ?? 'Not produced.'}</p>
        )}
        {unc && (
          <div className="mt-2 border-t border-border pt-2">
            <Row label="OOD risk" value={unc.ood_risk.replace(/_/g, ' ')} />
            <Row label="Evidence conflicts" value={unc.evidence_conflict_count} />
          </div>
        )}
      </Card>

      <Card
        title="CHHAYA · Source Hypothesis"
        right={
          <>
            <InfoTip label="Two stages of one question: CHHAYA · Source Hypothesis asks 'what kind of source is this?' (per case, from declared-likelihood-ratio evidence). CHHAYA · Vessel Evidence asks 'which vessel?' (per SAR tile). Not the same computation." />
            <StatusBadge tone={top ? 'ok' : 'muted'}>{top ? 'produced' : 'unavailable'}</StatusBadge>
          </>
        }
      >
        {top ? (
          <>
            <Row label="Top hypothesis" value={top.source_class.replace(/_/g, ' ')} />
            <Row label="Posterior" value={`${(top.posterior * 100).toFixed(1)}%`} />
            <Row label="Hypotheses" value={hyps.length} />
            <p className="mt-1.5 text-[11px] leading-snug text-[color-mix(in_oklch,var(--warn)_55%,black)]">
              Relative plausibility only — CHHAYA is <strong>uncalibrated</strong>; these are
              not calibrated probabilities.
            </p>
          </>
        ) : (
          <p className="text-[12px] text-muted-foreground">{intel.reason ?? 'No hypotheses composed.'}</p>
        )}
      </Card>

      <Card title="NYAYA — Attribution" right={<SectionStatus s={attr} />}>
        {attr.status === 'produced' && attr.value ? (
          <>
            <Row label="Top posterior" value={attr.value.top_posterior?.toFixed(3) ?? '—'} />
            <Row label="Candidates" value={attr.value.candidates?.length ?? 0} />
          </>
        ) : (
          <p className="text-[12px] text-muted-foreground">
            {attr.reason ?? 'Not produced — fail-closed, no attribution asserted.'}
          </p>
        )}
      </Card>

      <Card title="Validity gate" right={<SectionStatus s={val} />}>
        {val.status === 'produced' && val.value ? (
          <>
            <Row
              label="State"
              value={
                <StatusBadge tone={val.value.state === 'valid' ? 'ok' : 'warn'}>
                  {val.value.state.toUpperCase()}
                </StatusBadge>
              }
            />
            <Row
              label="Operational action"
              value={
                val.value.state === 'valid' || val.value.state === 'degraded'
                  ? 'allowed'
                  : 'not allowed'
              }
            />
            {(val.value.blocking_reasons?.length ?? 0) > 0 && (
              <ul className="mt-1.5 list-disc pl-4 text-[11px] text-muted-foreground">
                {val.value.blocking_reasons!.map((r: string) => (
                  <li key={r}>{r}</li>
                ))}
              </ul>
            )}
          </>
        ) : (
          <p className="text-[12px] text-muted-foreground">{val.reason ?? 'Gate did not run.'}</p>
        )}
      </Card>
    </div>
  )
}
