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
