'use client'

/**
 * Fetches ONE OperatorCase (via GET /v1/replay/{fixture}) and makes it
 * available to every component on the page through context, so a single
 * fetch backs the whole dashboard rather than each panel fetching
 * independently (Phase 26: avoid polling storms / repeated fetches of the
 * same case).
 */
import { createContext, useContext, useEffect, useState, type ReactNode } from 'react'
import { ApiError, getReplayOperatorCase } from './api'
import type { OperatorCase } from './operator-case-types'

export type FetchState =
  | { status: 'loading' }
  | { status: 'error'; error: string }
  | { status: 'success'; data: OperatorCase }

const OperatorCaseContext = createContext<FetchState>({ status: 'loading' })

export function OperatorCaseProvider({
  fixtureName,
  children,
}: {
  fixtureName: string
  children: ReactNode
}) {
  const [state, setState] = useState<FetchState>({ status: 'loading' })

  useEffect(() => {
    let cancelled = false
    setState({ status: 'loading' })
    getReplayOperatorCase(fixtureName)
      .then((data) => {
        if (!cancelled) setState({ status: 'success', data })
      })
      .catch((err) => {
        if (!cancelled) {
          setState({
            status: 'error',
            error: err instanceof ApiError ? err.message : String(err),
          })
        }
      })
    return () => {
      cancelled = true
    }
  }, [fixtureName])

  return (
    <OperatorCaseContext.Provider value={state}>{children}</OperatorCaseContext.Provider>
  )
}

export function useOperatorCase(): FetchState {
  return useContext(OperatorCaseContext)
}

/** Convenience for components that only render once data has loaded — pair
 * with an explicit loading/error boundary higher up the tree (see
 * `components/operator-case-boundary.tsx`) rather than checking `status`
 * ad hoc in every consumer. */
export function useOperatorCaseData(): OperatorCase | null {
  const state = useOperatorCase()
  return state.status === 'success' ? state.data : null
}
