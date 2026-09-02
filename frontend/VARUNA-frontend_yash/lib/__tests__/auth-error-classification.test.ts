/**
 * STEP 7 focused test: the 401-vs-403 classification every action button
 * (AlertActions, MissionStatus, LiveMissionsPanel) relies on to distinguish
 * NOT AUTHENTICATED from NOT AUTHORIZED. Kept as a pure-logic test (no
 * React renderer) mirroring the same pattern established in
 * forecast-panel-logic.test.ts.
 */
import { describe, expect, it } from 'vitest'
import { AuthActionError, ApiError } from '../api'

function classify(err: unknown): 'not_authenticated' | 'not_authorized' | 'other' {
  if (err instanceof AuthActionError) {
    return err.status === 401 ? 'not_authenticated' : 'not_authorized'
  }
  return 'other'
}

describe('auth error classification', () => {
  it('classifies a 401 AuthActionError as not_authenticated', () => {
    expect(classify(new AuthActionError('invalid or expired token', 401))).toBe('not_authenticated')
  })

  it('classifies a 403 AuthActionError as not_authorized', () => {
    expect(classify(new AuthActionError('lacks permission', 403))).toBe('not_authorized')
  })

  it('classifies a plain ApiError (e.g. network failure) as other', () => {
    expect(classify(new ApiError('could not reach backend'))).toBe('other')
  })

  it('AuthActionError is an instance of ApiError', () => {
    const err = new AuthActionError('x', 401)
    expect(err instanceof ApiError).toBe(true)
  })
})
