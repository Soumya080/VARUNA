/**
 * Phase 7 fix for the grey-placeholder bug (docs/product/HONESTY_LEDGER.md
 * #23): on fresh page load, `useRunStream()`'s `stageOrder` is `[]` and
 * `events` is `{}` (nothing has been live-streamed yet), so
 * `components/cockpit/cockpit-panels.tsx::RunTimeline` rendered all 13
 * stages grey — even though the composed `OperatorCase` (`oc`) was already
 * fully loaded via a plain GET and every stage had genuinely run. The most
 * important visual on the cockpit said "nothing happened" when everything
 * had.
 *
 * `deriveStageState` fixes this by falling back to `oc`'s own section
 * statuses (authoritative, available immediately on page load) whenever a
 * live SSE event for that stage doesn't exist yet, and tagging each result
 * with `source: 'live' | 'composed'` so a consumer can still distinguish
 * "this just streamed in" from "this was already true when the page
 * loaded" without ever rendering a false "pending" state for either.
 */
import type { StageEvent } from './use-run-stream'
import type { OperatorCase } from './operator-case-types'
import { STAGE_ORDER, type StageKey } from './stages'

export type DerivedStatus = 'produced' | 'not_yet_produced' | 'blocked' | 'error'

export interface DerivedStageState {
  stage: StageKey
  status: DerivedStatus
  reason: string | null
  elapsedMs: number | null
  source: 'live' | 'composed' | 'none'
}

function fromProducerStatus(status: string | undefined, reason: string | null | undefined): DerivedStatus {
  if (status === 'produced') return 'produced'
  if (status === 'blocked') return 'blocked'
  return 'not_yet_produced'
}

/**
 * `oc`-derived status for one stage, mirroring
 * `apps/api/routers/run_stream.py::_derived_status` and its per-stage
 * branches exactly — the same real sections, the same real fallback logic,
 * just evaluated client-side from data already in hand instead of waiting
 * for a live stream to say the same thing again.
 */
function composedStatus(oc: OperatorCase, stage: StageKey): { status: DerivedStatus; reason: string | null } {
  switch (stage) {
    case 'DATA':
      // No standalone "forcing" section on OperatorCase; DATA existing at
      // all is a precondition for detection ever having run.
      return oc.detection.status === 'produced'
        ? { status: 'produced', reason: null }
        : { status: 'not_yet_produced', reason: 'no detection means no forcing was consumed yet' }
    case 'NETRA':
    case 'DETECTION_EVIDENCE':
      return { status: fromProducerStatus(oc.detection.status, oc.detection.reason), reason: oc.detection.reason }
    case 'STARTING_POINT':
      return {
        status: oc.starting_point.status === 'STARTING_POINT_AVAILABLE' ? 'produced' : 'not_yet_produced',
        reason: oc.starting_point.reason,
      }
    case 'PRATIVARTAN':
      return { status: fromProducerStatus(oc.origin.status, oc.origin.reason), reason: oc.origin.reason }
    case 'PRAVAAH':
      return { status: fromProducerStatus(oc.forecast.status, oc.forecast.reason), reason: oc.forecast.reason }
    case 'CHHAYA':
      return {
        status: oc.intelligence.status === 'produced' && oc.intelligence.hypotheses ? 'produced' : 'not_yet_produced',
        reason: oc.intelligence.reason,
      }
    case 'NYAYA':
      return { status: fromProducerStatus(oc.attribution.status, oc.attribution.reason), reason: oc.attribution.reason }
    case 'VALIDITY':
      return { status: fromProducerStatus(oc.validity.status, oc.validity.reason), reason: oc.validity.reason }
    case 'NEXT_BEST_ACTION':
      return {
        status: oc.intelligence.next_best_action ? 'produced' : 'not_yet_produced',
        reason: oc.intelligence.reason,
      }
    case 'ALERT': {
      const n = oc.alerts.status === 'produced' ? (oc.alerts.value?.length ?? 0) : 0
      return {
        status: n > 0 ? 'produced' : 'not_yet_produced',
        reason: n > 0 ? null : 'no material change met the operator-attention threshold for this case',
      }
    }
    case 'MISSION':
      return { status: fromProducerStatus(oc.mission.status, oc.mission.reason), reason: oc.mission.reason }
    case 'PRAMAN':
      // PRAMAN provenance exists once a case has been composed at all —
      // there's no dedicated SectionEnvelope for it on OperatorCase.
      return { status: 'produced', reason: null }
  }
}

export function deriveStageState(
  oc: OperatorCase | null,
  events: Record<string, StageEvent>,
  phase: string,
): DerivedStageState[] {
  return STAGE_ORDER.map((stage) => {
    const live = events[stage]
    if (live) {
      const status: DerivedStatus =
        live.status === 'produced'
          ? 'produced'
          : live.status === 'blocked' || live.status === 'error'
            ? (live.status as DerivedStatus)
            : 'not_yet_produced'
      return {
        stage,
        status,
        reason: live.reason,
        elapsedMs: live.elapsed_ms,
        source: 'live',
      }
    }
    if (oc) {
      const { status, reason } = composedStatus(oc, stage)
      return { stage, status, reason, elapsedMs: null, source: 'composed' }
    }
    return {
      stage,
      status: 'not_yet_produced',
      reason: phase === 'running' ? 'running…' : null,
      elapsedMs: null,
      source: 'none',
    }
  })
}
