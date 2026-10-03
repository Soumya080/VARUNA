'use client'

/**
 * Hypothesis waterfall — Phase 10B (docs/product/HONESTY_LEDGER.md #16).
 *
 * Renders CHHAYA-H's real per-factor reasoning for one source-class
 * hypothesis: prior -> posterior as two bookend meters, and every
 * `FactorContribution` that moved it as a signed, labelled bar. This is
 * the most important honesty affordance the backend computes and nothing
 * rendered before this: `measured: false` bars — a DECLARED ASSUMPTION,
 * not data — render visually distinct (hatched, muted) from `measured:
 * true` ones, exactly mirroring the distinction the engine itself already
 * makes (see `packages/varuna_chhaya/hypothesis_engine.py`'s own
 * docstring on why a declared-prior engine is honest about not being a
 * trained model).
 *
 * Deliberately NOT a literal stacked log-odds cascade — this repo does not
 * claim more precision than a bar-per-factor view honestly supports.
 * `log_likelihood_ratio` values are shown in their real natural-log units,
 * not converted into a fabricated visual metaphor.
 */
import type { SourceHypothesisValue } from '@/lib/operator-case-types'
import { Meter, InfoTip, StatusBadge } from '@/components/primitives'

const HATCH_ID = 'waterfall-hatch'

function HatchDefs() {
  return (
    <defs>
      <pattern id={HATCH_ID} width={4} height={4} patternTransform="rotate(45)" patternUnits="userSpaceOnUse">
        <line x1={0} y1={0} x2={0} y2={4} stroke="currentColor" strokeWidth={1.5} />
      </pattern>
    </defs>
  )
}

function FactorBar({ factor }: { factor: SourceHypothesisValue['supporting'][number] }) {
  const llr = factor.log_likelihood_ratio
  const magnitude = Math.min(1, Math.abs(llr) / 1.2) // _STRONG ~= ln(3.0) ~= 1.10; clamp for display
  const positive = llr > 0
  const widthPct = magnitude * 50

  return (
    <li className="space-y-1">
      <div className="flex items-center gap-1.5">
        <span className="min-w-0 flex-1 truncate font-mono text-[11px] text-foreground">{factor.factor}</span>
        {!factor.measured && (
          <span className="flex items-center gap-1">
            <StatusBadge tone="warn" className="px-1 py-0 text-[8px]">
              declared assumption
            </StatusBadge>
            <InfoTip label="measured: false — this factor is a stated modelling assumption, not a value derived from measured evidence. The engine itself distinguishes the two; this is that distinction, finally visible." />
          </span>
        )}
        <span className="shrink-0 font-mono text-[10px] tabular-nums text-muted-foreground">
          {llr >= 0 ? '+' : ''}
          {llr.toFixed(2)}
        </span>
      </div>
      <div className="relative h-3 w-full overflow-hidden rounded-[2px] bg-muted">
        <div className="absolute left-1/2 top-0 h-full w-px bg-border" />
        <svg className="absolute inset-0 h-full w-full" preserveAspectRatio="none">
          {!factor.measured && <HatchDefs />}
          <rect
            x={positive ? '50%' : `${50 - widthPct}%`}
            y={0}
            width={`${widthPct}%`}
            height="100%"
            fill={
              !factor.measured
                ? `url(#${HATCH_ID})`
                : positive
                  ? 'var(--ok)'
                  : 'var(--destructive)'
            }
            className={!factor.measured ? (positive ? 'text-[var(--ok)]' : 'text-destructive') : undefined}
            opacity={factor.measured ? 0.75 : 0.6}
          />
        </svg>
      </div>
      <p className="text-[10px] leading-snug text-muted-foreground">{factor.detail}</p>
    </li>
  )
}

export function HypothesisWaterfall({ hypothesis }: { hypothesis: SourceHypothesisValue }) {
  const factors = [...hypothesis.supporting, ...hypothesis.contradicting]

  return (
    <div className="space-y-3">
      <div className="grid grid-cols-2 gap-3">
        <div>
          <div className="mb-1 flex items-center justify-between text-[11px] text-muted-foreground">
            <span>Prior</span>
            <span className="font-mono text-foreground">{(hypothesis.prior * 100).toFixed(1)}%</span>
          </div>
          <Meter value={hypothesis.prior * 100} tone="muted" />
        </div>
        <div>
          <div className="mb-1 flex items-center justify-between text-[11px] text-muted-foreground">
            <span>Posterior</span>
            <span className="font-mono text-foreground">{(hypothesis.posterior * 100).toFixed(1)}%</span>
          </div>
          <Meter value={hypothesis.posterior * 100} tone={hypothesis.posterior >= hypothesis.prior ? 'teal' : 'saffron'} />
        </div>
      </div>

      {factors.length === 0 ? (
        <p className="text-[11px] text-muted-foreground">
          No factors bore on {hypothesis.source_class.replace(/_/g, ' ')} — posterior equals the declared prior.
        </p>
      ) : (
        <ul className="space-y-2.5">
          {factors.map((f, i) => (
            <FactorBar key={`${f.factor}-${i}`} factor={f} />
          ))}
        </ul>
      )}

      <p className="border-t border-border pt-2 text-[11px] italic leading-snug text-muted-foreground">
        {hypothesis.rationale}
      </p>
    </div>
  )
}
