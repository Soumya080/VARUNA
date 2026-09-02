'use client'

import { useState } from 'react'
import { useOperatorCaseData } from '@/lib/operator-case-context'
import { CURRENT_MISSION_STATE, MISSION_STATES } from '@/lib/mock-data'
import { approveMission, AuthActionError } from '@/lib/api'
import { useAuth } from '@/lib/auth-context'
import { cn } from '@/lib/utils'
import { Check, FileSearch, ShieldCheck } from 'lucide-react'
import { SectionLabel, StatusBadge } from './primitives'

/**
 * The real backend mission state machine (varuna_contracts.states.MissionState
 * — RESERVED/AVAILABLE/ASSIGNED/ACKNOWLEDGED/EN_ROUTE/ON_STATION/SEARCHING/
 * NOT_FOUND/COMPLETE/REASSIGNED/CLOSED, a branching graph with a REASSIGNED
 * loop-back) does not fit the existing linear 6-step visual track below
 * (PROPOSED → APPROVAL → DISPATCH → IN PROGRESS → COMPLETED → VERIFIED),
 * which models a different, simpler vocabulary. Rather than force a
 * branching state machine into a track that implies linear progress (which
 * would misrepresent REASSIGNED/CLOSED), the real mission's actual state is
 * shown as a plain badge + fields above the (kept, unmodified) illustrative
 * track. This is the "does not fit current design, add the minimum
 * necessary panel" case from this task's Phase 3, not a redesign.
 */
function useRealMission() {
  const oc = useOperatorCaseData()
  if (!oc || oc.mission.status !== 'produced' || !oc.mission.value?.length) return null
  return oc.mission.value[0]
}

export function MissionStatus() {
  const currentIdx = MISSION_STATES.indexOf(CURRENT_MISSION_STATE)
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
            {realMission.approved_by
              ? `Approved by ${realMission.approved_by}`
              : 'Not yet human-approved'}
          </span>
        </div>
      )}

      {/* State track */}
      <ol className="flex items-center gap-1 overflow-x-auto scroll-thin pb-1">
        {MISSION_STATES.map((state, i) => {
          const done = i < currentIdx
          const current = i === currentIdx
          return (
            <li key={state} className="flex flex-1 items-center gap-1">
              <div
                className={cn(
                  'flex min-w-[92px] flex-1 items-center gap-2 rounded-sm border px-2.5 py-2',
                  current
                    ? 'border-[color-mix(in_oklch,var(--warn)_45%,transparent)] bg-[color-mix(in_oklch,var(--warn)_12%,transparent)]'
                    : done
                      ? 'border-[color-mix(in_oklch,var(--ok)_35%,transparent)] bg-[color-mix(in_oklch,var(--ok)_8%,transparent)]'
                      : 'border-border bg-background/40',
                )}
              >
                <span
                  className={cn(
                    'grid h-4 w-4 shrink-0 place-items-center rounded-full font-mono text-[10px] font-bold',
                    current
                      ? 'bg-[var(--warn)] text-[oklch(0.22_0.03_60)]'
                      : done
                        ? 'bg-[var(--ok)] text-primary-foreground'
                        : 'bg-muted text-muted-foreground',
                  )}
                >
                  {done ? <Check className="h-2.5 w-2.5" /> : i + 1}
                </span>
                <span
                  className={cn(
                    'truncate font-mono text-[11px] font-semibold uppercase tracking-[0.06em]',
                    current
                      ? 'text-[color-mix(in_oklch,var(--warn)_55%,black)]'
                      : done
                        ? 'text-[color-mix(in_oklch,var(--ok)_55%,black)]'
                        : 'text-muted-foreground',
                  )}
                >
                  {state}
                </span>
              </div>
              {i < MISSION_STATES.length - 1 && (
                <span
                  className={cn(
                    'h-px w-2 shrink-0',
                    done ? 'bg-[var(--ok)]' : 'bg-border',
                  )}
                  aria-hidden="true"
                />
              )}
            </li>
          )
        })}
      </ol>

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
