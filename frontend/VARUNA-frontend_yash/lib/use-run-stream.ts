'use client'

/**
 * Consumes the backend's real SSE execution stream
 * (`GET /v1/run/{fixture}/stream`). Every timeline entry here comes from an
 * actual backend event — there is no client-side timer, no simulated
 * progress and no optimistic "probably succeeded" state.
 */
import { useCallback, useRef, useState } from 'react'
import { API_BASE_URL } from './api'

export interface StageEvent {
  stage: string
  status: string
  elapsed_ms: number
  stage_runtime_ms: number | null
  reason: string | null
  case_id: string | null
  run_id: string | null
  detail: Record<string, unknown>
}

export interface RunSummary {
  case_id: string
  run_id: string | null
  elapsed_ms: number
  workflow_ms: number
  compose_ms: number
  recommendation: string
  engine_mode: string | null
}

export type RunPhase = 'idle' | 'running' | 'complete' | 'failed'

export function useRunStream() {
  const [phase, setPhase] = useState<RunPhase>('idle')
  const [stageOrder, setStageOrder] = useState<string[]>([])
  const [events, setEvents] = useState<Record<string, StageEvent>>({})
  const [summary, setSummary] = useState<RunSummary | null>(null)
  const [error, setError] = useState<string | null>(null)
  const esRef = useRef<EventSource | null>(null)

  const run = useCallback((fixture: string, onComplete?: () => void) => {
    esRef.current?.close()
    setPhase('running')
    setEvents({})
    setSummary(null)
    setError(null)

    const es = new EventSource(
      `${API_BASE_URL}/v1/run/${encodeURIComponent(fixture)}/stream`,
    )
    esRef.current = es

    es.onmessage = (e) => {
      let msg: Record<string, unknown>
      try {
        msg = JSON.parse(e.data)
      } catch {
        return
      }
      if (msg.type === 'run_started') {
        setStageOrder((msg.stages as string[]) ?? [])
      } else if (msg.type === 'stage') {
        const ev = msg as unknown as StageEvent
        setEvents((prev) => ({ ...prev, [ev.stage]: ev }))
      } else if (msg.type === 'run_complete') {
        setSummary(msg as unknown as RunSummary)
        setPhase('complete')
        es.close()
        onComplete?.()
      } else if (msg.type === 'run_failed') {
        setError(String(msg.error ?? 'run failed'))
        setPhase('failed')
        es.close()
      }
    }

    es.onerror = () => {
      // EventSource fires onerror on normal close too; only surface it if
      // the run never reached a terminal event.
      setPhase((p) => {
        if (p === 'running') {
          setError(`Lost connection to ${API_BASE_URL}/v1/run/${fixture}/stream`)
          return 'failed'
        }
        return p
      })
      es.close()
    }
  }, [])

  return { phase, stageOrder, events, summary, error, run }
}
