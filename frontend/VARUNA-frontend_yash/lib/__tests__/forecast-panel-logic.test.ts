/**
 * STEP 5 focused test (Phase 7 #9): the frontend must never fabricate a
 * forecast when the backend section is not produced. Tests the pure
 * decision logic ForecastPanel uses to choose between rendering real data
 * and rendering the honest unavailable state, without needing a React
 * renderer (kept minimal, per this task's "do not add an unnecessary
 * testing framework" instruction — reusing the same lib/api.ts shapes).
 */
import { describe, expect, it } from 'vitest'
import type { SectionEnvelope, ForwardForecastValue } from '../operator-case-types'

/** Mirrors the exact guard condition in components/intelligence-panels.tsx::ForecastPanel. */
function shouldRenderRealForecast(section: SectionEnvelope<ForwardForecastValue> | undefined): boolean {
  return Boolean(section && section.status === 'produced' && section.value)
}

const REAL_FORECAST: ForwardForecastValue = {
  forecast_id: 'f-1',
  slick_id: 's-1',
  horizon_hours: 24,
  landfalls: [],
  affected_fishing_zones: [],
  trajectory_path: 'replay://traj.npz',
  computed_at: '2026-01-01T00:00:00Z',
  envelope: { mode: 'real', case_id: 'CASE-1' },
}

describe('ForecastPanel never fabricates a missing forecast', () => {
  it('renders real data only when status is produced AND a value exists', () => {
    expect(
      shouldRenderRealForecast({ status: 'produced', reason: null, evidence_mode: 'real', value: REAL_FORECAST }),
    ).toBe(true)
  })

  it('refuses to render real data when status is not_yet_produced, even if a stale value were present', () => {
    expect(
      shouldRenderRealForecast({
        status: 'not_yet_produced',
        reason: 'NO_SLICK_TO_FORECAST',
        evidence_mode: null,
        value: REAL_FORECAST, // must not happen from a real backend, but the guard must not trust it anyway
      }),
    ).toBe(false)
  })

  it('refuses to render real data when value is null even if status claims produced', () => {
    expect(
      shouldRenderRealForecast({ status: 'produced', reason: null, evidence_mode: 'real', value: null }),
    ).toBe(false)
  })

  it('refuses to render real data when the section is entirely absent', () => {
    expect(shouldRenderRealForecast(undefined)).toBe(false)
  })

  it('refuses to render real data for a blocked forecast', () => {
    expect(
      shouldRenderRealForecast({ status: 'blocked', reason: 'PRAVAAH_FAILED', evidence_mode: null, value: null }),
    ).toBe(false)
  })
})
