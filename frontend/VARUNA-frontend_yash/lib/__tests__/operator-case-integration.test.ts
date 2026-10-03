/**
 * Focused tests (STEP 4, Phase 16) for the highest-risk frontend behaviors:
 * EvidenceMode/engine_mode rendering never collapsing or mislabeling, and
 * the API client's error handling. Deliberately not a large test suite —
 * these are the specific correctness properties this task's own Phase 5
 * ("never collapse REAL/REPLAY/SIMULATED") depends on.
 */
import { describe, expect, it, vi, beforeEach, afterEach } from 'vitest'
import {
  ENGINE_MODE_LABEL,
  ENGINE_MODE_TONE,
  EVIDENCE_MODE_LABEL,
  EVIDENCE_MODE_TONE,
} from '../../components/evidence-mode-badge'
import { ApiError, getReplayOperatorCase, listReplayFixtures } from '../api'
import type { EngineModeValue, EvidenceModeValue } from '../operator-case-types'

describe('EvidenceMode / engine_mode vocabulary completeness', () => {
  it('has a distinct label for every real EngineModeValue', () => {
    const modes: Array<NonNullable<EngineModeValue>> = ['real', 'replay', 'simulated']
    const labels = modes.map((m) => ENGINE_MODE_LABEL[m])
    expect(new Set(labels).size).toBe(modes.length) // no two modes share a label
  })

  it('never gives "replay" the same tone as "real" (Phase 5: never make replay look like real)', () => {
    expect(ENGINE_MODE_TONE.replay).not.toBe(ENGINE_MODE_TONE.real)
  })

  it('never gives "simulated" the same tone as "real" evidence', () => {
    const modes: EvidenceModeValue[] = ['real', 'simulated', 'unavailable']
    for (const m of modes) {
      expect(EVIDENCE_MODE_LABEL[m]).toBeTruthy()
    }
    expect(EVIDENCE_MODE_TONE.simulated).not.toBe(EVIDENCE_MODE_TONE.real)
    expect(EVIDENCE_MODE_TONE.unavailable).not.toBe(EVIDENCE_MODE_TONE.real)
  })
})

describe('API client error handling', () => {
  const originalFetch = global.fetch

  afterEach(() => {
    global.fetch = originalFetch
    vi.restoreAllMocks()
  })

  it('throws ApiError (not a silent fallback) when the backend is unreachable', async () => {
    global.fetch = vi.fn().mockRejectedValue(new Error('ECONNREFUSED'))
    await expect(getReplayOperatorCase('CASE-VALID')).rejects.toBeInstanceOf(ApiError)
  })

  it('throws ApiError with the backend detail message on a 404', async () => {
    global.fetch = vi.fn().mockResolvedValue({
      ok: false,
      status: 404,
      statusText: 'Not Found',
      json: async () => ({ detail: "Unknown replay fixture 'NOPE'" }),
    } as Response)
    await expect(getReplayOperatorCase('NOPE')).rejects.toThrow("Unknown replay fixture 'NOPE'")
  })

  it('does not fabricate a fixtures list when the backend errors', async () => {
    global.fetch = vi.fn().mockResolvedValue({
      ok: false,
      status: 500,
      statusText: 'Internal Server Error',
      json: async () => {
        throw new Error('not json')
      },
    } as unknown as Response)
    await expect(listReplayFixtures()).rejects.toBeInstanceOf(ApiError)
  })
})
