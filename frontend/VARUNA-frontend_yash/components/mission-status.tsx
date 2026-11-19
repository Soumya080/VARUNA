'use client'

import { useState } from 'react'
import { useOperatorCaseData } from '@/lib/operator-case-context'
import { approveMission, AuthActionError } from '@/lib/api'
import { useAuth } from '@/lib/auth-context'
import { cn } from '@/lib/utils'
import { FileSearch, ShieldCheck } from 'lucide-react'
import { SectionLabel, StatusBadge } from './primitives'
import { MissionFsmGraph } from './mission-fsm'

/**
 * Phase 6A (docs/product/HONESTY_LEDGER.md #18): this used to render a
 * hardcoded linear 6-step track (PROPOSED -> APPROVAL -> DISPATCH -> IN
 * PROGRESS -> COMPLETED -> VERIFIED, `CURRENT_MISSION_STATE='APPROVAL'` a
 * literal never tied to any real mission) alongside a plain badge showing
 * the real state, because the real backend FSM (13 states, branching, a
 * REASSIGNED loop-back) didn't fit that track. It's replaced outright by
 * `MissionFsmGraph` below, which renders the actual state machine as a
 * branching graph — no more fake track to keep in sync with reality.
 */
function useRealMission() {
  const oc = useOperatorCaseData()
  if (!oc || oc.mission.status !== 'produced' || !oc.mission.value?.length) return null
  return oc.mission.value[0]
}

export function MissionStatus() {
  const realMission = useRealMission()
  const { session, isAuthenticated, logout } = useAuth()
  const [authMessage, setAuthMessage] = useState<string | null>(null)
  const [pending, setPending] = useState(false)

  async function requestAuthorization() {
    if (!realMission) return
    if (!isAuthenticated || !session) {
      setAuthMessage('NOT AUTHENTICATED — sign in (top right) first.')
      return
    }
    setPending(true)
    setAuthMessage(null)
    try {
      await approveMission(realMission.mission_id, session.username)
      setAuthMessage('Authorized — confirmed by backend.')
    } catch (err) {
      if (err instanceof AuthActionError) {
        if (err.status === 401) {
          logout()
          setAuthMessage('NOT AUTHENTICATED — session invalid or expired. Please sign in again.')
        } else {
          setAuthMessage(`NOT AUTHORIZED — ${session.role} does not hold mission-approval permission.`)
        }
      } else {
        setAuthMessage(err instanceof Error ? err.message : 'Request failed.')
      }
    } finally {
      setPending(false)
    }
  }

  return (
    <section className="rounded-sm border border-border bg-card p-3.5">
      <div className="mb-3 flex items-center justify-between">
        <SectionLabel>Mission Status</SectionLabel>
        <span className="font-mono text-[10px] uppercase tracking-[0.1em] text-[color-mix(in_oklch,var(--warn)_55%,black)]">
          Awaiting authorization
        </span>
      </div>

      {realMission && (
        <div className="mb-3 flex flex-wrap items-center gap-x-4 gap-y-1.5 rounded-sm border border-border bg-muted/30 px-3 py-2">
          <span className="font-mono text-[11px] text-muted-foreground">
            {realMission.mission_id}
          </span>
          <StatusBadge tone={realMission.state === 'assigned' ? 'ok' : 'muted'} dot>
            {realMission.state}
          </StatusBadge>
          <span className="font-mono text-[11px] text-muted-foreground">
            Asset: {realMission.asset_id ?? '—'}
          </span>
          <span className="font-mono text-[11px] text-muted-foreground">
            {realMission.human_approved_by
              ? `Approved by ${realMission.human_approved_by}`
              : 'Not yet human-approved'}
          </span>
        </div>
      )}

      {/* Real mission FSM graph (Phase 6A) */}
      {realMission ? (
        <MissionFsmGraph missionId={realMission.mission_id} />
      ) : (
        <p className="text-[11px] text-muted-foreground">No real mission record on this case.</p>
      )}

      {/* Actions */}
      <div className="mt-3.5 flex flex-col gap-2 sm:flex-row">
        <button
          type="button"
          disabled={!realMission || pending}
          onClick={requestAuthorization}
          title={
            realMission
              ? 'Genuinely calls POST /v1/missions/{id}/approve. No login endpoint exists in this deployment yet, so this will honestly report NOT AUTHORIZED rather than simulate success.'
              : 'No real mission record is available on this case.'
          }
          className="flex flex-1 items-center justify-center gap-1.5 rounded-sm bg-primary px-4 py-2.5 text-[13px] font-semibold uppercase tracking-[0.08em] text-primary-foreground transition-colors hover:bg-[var(--navy-muted)] disabled:cursor-not-allowed disabled:opacity-50"
        >
          <ShieldCheck className="h-4 w-4" />
          Request Authorization
        </button>
        <button
          type="button"
          onClick={() =>
            document
              .getElementById('evidence-health-panel')
              ?.scrollIntoView({ behavior: 'smooth', block: 'start' })
          }
          className="flex items-center justify-center gap-1.5 rounded-sm border border-border bg-background px-4 py-2.5 text-[13px] font-semibold uppercase tracking-[0.08em] text-foreground transition-colors hover:bg-muted sm:flex-none"
        >
          <FileSearch className="h-4 w-4" />
          Review Evidence
        </button>
      </div>
      {authMessage && (
        <p
          className={cn(
            'mt-2 text-[12px]',
            authMessage.startsWith('Authorized') ? 'text-[var(--ok)]' : 'text-destructive',
          )}
        >
          {authMessage}
        </p>
      )}
    </section>
  )
}
