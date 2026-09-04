'use client'

import { useOperatorCaseData } from '@/lib/operator-case-context'
import { CASE_SUMMARY, formatLat, formatLng, type SummaryMetric } from '@/lib/mock-data'
import { cn } from '@/lib/utils'

const toneText: Record<string, string> = {
  ok: 'text-[color-mix(in_oklch,var(--ok)_60%,black)]',
  warn: 'text-[color-mix(in_oklch,var(--warn)_55%,black)]',
  saffron: 'text-[color-mix(in_oklch,var(--saffron)_52%,black)]',
  default: 'text-foreground',
}

/**
 * Real values from the unified OperatorCase where the backend produced
 * them; explicit "—" (never a fabricated number) where it did not. Replaces
 * the previous all-mock CASE_SUMMARY constant for the fields the backend
 * contract actually carries (observation time, origin, validity,
 * recommendation). Fields the contract has no equivalent for yet
 * (drift-window duration is not a top-level OperatorCase field) fall back
 * to the existing mock metric, unchanged, until a real field exists.
 */
function useSummaryMetrics(): SummaryMetric[] {
  const oc = useOperatorCaseData()
  if (!oc) return CASE_SUMMARY

  // Starting point comes from the backend's explicit contract
  // (OperatorCase.starting_point), NOT from `origin.value.centroid` — PhiField
  // has no `centroid` field at all, so the previous read was always undefined
  // and a fully-produced origin stage rendered as "not produced".
  const sp = oc.starting_point
  const spPoint = sp?.status === 'STARTING_POINT_AVAILABLE' ? sp.point : null

  const validityValue = oc.validity.value
  const validityState = validityValue?.state ?? null
  // `allows_operational_action` is a Python @property on the ValidityState
  // enum and is never serialised (same class of bug as SourceHypothesis
  // `.top` in STEP 5). Derive it from `state` exactly as the backend enum
  // does — reading the absent field made a VALID gate render as
  // "does not allow operational action".
  const allowsAction =
    validityState === 'valid' || validityState === 'degraded'

  const metrics: SummaryMetric[] = [
    {
      // M3 fix (docs/product/HONESTY_LEDGER.md #5): used to show the raw
      // Phi coordinate (`obs_time_hours`, legitimately negative for a
      // historical case — e.g. -78236.0 — and confusing labelled "relative
      // hours"). Shows the real wall-clock `observation_time` now; the Phi
      // coordinate is still available (`phi_time_coordinate_hours`) but is
      // an internal detail, not the headline number.
      label: 'Observation',
      primary:
        oc.observation.status === 'produced' && oc.observation.value?.observation_time
          ? new Date(oc.observation.value.observation_time).toISOString().slice(0, 16).replace('T', ' ') + 'Z'
          : '—',
      secondary: oc.observation.status === 'produced'
        ? (oc.observation.value?.observation_time ? 'observed at' : 'observation time unknown')
        : oc.observation.reason ?? 'not produced',
      tone: oc.observation.status === 'produced' ? 'default' : 'warn',
    },
    // Drift window has no direct OperatorCase field; keep the existing
    // placeholder metric rather than inventing one.
    CASE_SUMMARY.find((m) => m.label === 'Drift Window') ?? CASE_SUMMARY[1],
    {
      label: 'Starting Point',
      // formatLat/formatLng emit the correct hemisphere (N/S, E/W); the
      // previous code hardcoded "° N"/"° E", which would mislabel the
      // western-hemisphere MC20 coordinates this case actually carries.
      primary: spPoint ? formatLat(spPoint.lat) : '—',
      secondary: spPoint
        ? `${formatLng(spPoint.lon)} · ${sp.source.replace(/_/g, ' ')}`
        : sp?.reason ?? sp?.status ?? 'not produced',
      tone: spPoint ? 'saffron' : 'warn',
    },
    {
      label: 'Attribution',
      primary:
        oc.attribution.status === 'produced' && oc.attribution.value
          ? oc.attribution.value.top_posterior.toFixed(2)
          : '—',
      secondary:
        oc.attribution.status === 'produced'
          ? 'top posterior (NYAYA)'
          : oc.attribution.reason ?? 'not produced',
      tone: oc.attribution.status === 'produced' ? 'ok' : 'warn',
    },
    {
      label: 'Validity Gate',
      primary: validityState ? validityState.toUpperCase() : '—',
      secondary: validityValue
        ? allowsAction
          ? 'allows operational action'
          : 'does not allow operational action'
        : oc.validity.reason ?? 'not produced',
      tone: validityState === 'valid' ? 'ok' : validityState ? 'warn' : 'default',
    },
  ]
  return metrics
}

export function CaseSummary() {
  const metrics = useSummaryMetrics()
  return (
    <section aria-label="Case summary" className="grid grid-cols-2 gap-2 sm:grid-cols-3 lg:grid-cols-5">
      {metrics.map((m) => (
        <div
          key={m.label}
          className="rounded-sm border border-border bg-card px-3 py-2.5"
        >
          <div className="font-mono text-[10px] font-medium uppercase tracking-[0.12em] text-muted-foreground">
            {m.label}
          </div>
          <div
            className={cn(
              'mt-1 font-mono text-[16px] font-semibold leading-none tabular-nums',
              toneText[m.tone ?? 'default'],
            )}
          >
            {m.primary}
          </div>
          {m.secondary && (
            <div className="mt-1 text-[11px] leading-none text-muted-foreground">
              {m.secondary}
            </div>
          )}
        </div>
      ))}
    </section>
  )
}
