'use client'

/**
 * Phase 5 (frontend integration track): make EvidenceMode and engine_mode
 * visually obvious and NEVER collapse them. Two distinct badges, not one —
 * `engine_mode` answers "how was this run produced," a section's
 * `evidence_mode` answers "how real is THIS evidence." Reuses the existing
 * `StatusBadge` primitive and tone system; no new visual language.
 */
import { StatusBadge } from './primitives'
import type { EngineModeValue, EvidenceModeValue } from '@/lib/operator-case-types'

export const ENGINE_MODE_LABEL: Record<NonNullable<EngineModeValue>, string> = {
  real: 'Real Execution',
  replay: 'Replay',
  simulated: 'Simulated',
}

export const ENGINE_MODE_TONE: Record<NonNullable<EngineModeValue>, 'ok' | 'warn' | 'saffron'> = {
  real: 'ok',
  replay: 'warn',
  simulated: 'saffron',
}

export function EngineModeBadge({ mode }: { mode: EngineModeValue }) {
  if (mode === null) {
    return (
      <StatusBadge tone="muted" dot>
        Engine Mode Unknown
      </StatusBadge>
    )
  }
  return (
    <StatusBadge tone={ENGINE_MODE_TONE[mode]} dot>
      {ENGINE_MODE_LABEL[mode]}
    </StatusBadge>
  )
}

export const EVIDENCE_MODE_LABEL: Record<EvidenceModeValue, string> = {
  real: 'Real Evidence',
  simulated: 'Simulated Evidence',
  unavailable: 'Evidence Unavailable',
}

export const EVIDENCE_MODE_TONE: Record<EvidenceModeValue, 'ok' | 'saffron' | 'muted'> = {
  real: 'ok',
  simulated: 'saffron',
  unavailable: 'muted',
}

export function EvidenceModeBadge({
  mode,
  compact = false,
}: {
  mode: EvidenceModeValue | null
  compact?: boolean
}) {
  if (mode === null) {
    return (
      <StatusBadge tone="muted" className={compact ? 'px-1 py-0 text-[9px]' : undefined}>
        —
      </StatusBadge>
    )
  }
  return (
    <StatusBadge
      tone={EVIDENCE_MODE_TONE[mode]}
      className={compact ? 'px-1 py-0 text-[9px]' : undefined}
    >
      {compact ? mode.toUpperCase() : EVIDENCE_MODE_LABEL[mode]}
    </StatusBadge>
  )
}

/* ------------------------------------------------------------------ */
/* EvidenceStateStrip — Phase 6C (docs/product/HONESTY_LEDGER.md #20)   */
/* ------------------------------------------------------------------ */

/**
 * Every `EvidenceEnvelope` (packages/varuna_contracts/evidence.py) carries
 * FIVE state axes beyond `mode` — `trust`, `calibration_state`,
 * `validity_state`, `degradation_state`, `anomaly_flags` — served on every
 * artifact and rendered nowhere before this. Real, honest information
 * design: muted when nominal, loud when not, so a reader isn't asked to
 * parse five badges to find the one that matters.
 */
export interface EvidenceEnvelopeStateView {
  trust?: 'trusted' | 'degraded' | 'conflicted' | 'quarantined'
  calibration_state?: 'calibrated' | 'uncalibrated' | 'out_of_domain' | 'not_applicable'
  validity_state?: 'valid' | 'degraded' | 'restricted' | 'inconclusive'
  degradation_state?:
    | 'nominal' | 'partial_input_loss' | 'fallback_source' | 'reduced_ensemble'
    | 'stale_input' | 'cached_replay'
  anomaly_flags?: string[]
  [key: string]: unknown
}

const NOMINAL_VALUES = new Set(['trusted', 'calibrated', 'not_applicable', 'valid', 'nominal'])

function axisTone(value: string | undefined): 'ok' | 'warn' | 'muted' {
  if (!value) return 'muted'
  return NOMINAL_VALUES.has(value) ? 'ok' : 'warn'
}

export function EvidenceStateStrip({ envelope }: { envelope: EvidenceEnvelopeStateView | null | undefined }) {
  if (!envelope) return null
  const flags = envelope.anomaly_flags ?? []
  const cells: Array<{ key: string; label: string; value: string; tone: 'ok' | 'warn' | 'muted' }> = [
    { key: 'trust', label: 'Trust', value: envelope.trust ?? '—', tone: axisTone(envelope.trust) },
    {
      key: 'validity',
      label: 'Validity',
      value: envelope.validity_state ?? '—',
      tone: axisTone(envelope.validity_state),
    },
    {
      key: 'degradation',
      label: 'Degradation',
      value: envelope.degradation_state ?? '—',
      tone: axisTone(envelope.degradation_state),
    },
    {
      key: 'calibration',
      label: 'Calibration',
      value: envelope.calibration_state ?? '—',
      tone: axisTone(envelope.calibration_state),
    },
    {
      key: 'anomalies',
      label: 'Anomalies',
      value: flags.length === 0 ? 'none' : `${flags.length}`,
      tone: flags.length === 0 ? 'ok' : 'warn',
    },
  ]

  return (
    <div className="flex flex-wrap items-center gap-1">
      {cells.map((c) => (
        <span
          key={c.key}
          title={
            c.key === 'anomalies' && flags.length > 0
              ? flags.join(', ')
              : `${c.label}: ${c.value}`
          }
          className={
            'inline-flex items-center gap-0.5 rounded-[3px] border px-1 py-0 font-mono text-[9px] uppercase tracking-[0.04em] ' +
            (c.tone === 'ok'
              ? 'border-border text-muted-foreground'
              : c.tone === 'warn'
                ? 'border-[color-mix(in_oklch,var(--warn)_45%,transparent)] bg-[color-mix(in_oklch,var(--warn)_10%,transparent)] text-[color-mix(in_oklch,var(--warn)_55%,black)]'
                : 'border-border text-muted-foreground/60')
          }
        >
          {c.label}: {c.value.replace(/_/g, ' ')}
        </span>
      ))}
    </div>
  )
}
