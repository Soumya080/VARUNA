'use client'

import { useEffect, useState } from 'react'
import { SectionLabel, StatusBadge } from '@/components/primitives'
import { MissionFsmGraph } from '@/components/mission-fsm'
import { OperatorCaseProvider, useOperatorCaseData } from '@/lib/operator-case-context'
import { OperatorCaseBoundary } from '@/components/operator-case-boundary'
import { approveMission, AuthActionError, getMissionAudit, listMissions } from '@/lib/api'
import { useAuth } from '@/lib/auth-context'
import { Check, ShieldCheck } from 'lucide-react'
import { cn } from '@/lib/utils'

/**
 * STEP 6: replaces the previous fully-hardcoded `MISSIONS`/`MISSION_HISTORY`
 * arrays (docs/product/ALERT_OPERATIONAL_DIAGNOSTIC.md item 18). Two real,
 * currently-separate data sources are shown honestly rather than merged
 * into one fabricated list:
 *   1. `OperatorCase.mission` — the replay fixture's mission, correlated
 *      with the rest of the operator cockpit (same case as Alert Center).
 *   2. `GET /v1/missions` — the live `MissionService` store, the one
 *      `POST /v1/missions/{id}/approve` actually authorizes against.
 * These are not the same record today (the replay fixture builds its
 * MissionRecord directly, not through MissionService) — that gap is
 * documented, not silently papered over by pretending they're one list.
 */

function statusTone(status: string) {
  if (status === 'assigned' || status === 'en_route' || status === 'on_station') return 'ok' as const
  if (status === 'available' || status === 'reserved') return 'warn' as const
  if (status === 'complete' || status === 'closed') return 'muted' as const
  return 'muted' as const
}

function ReplayCaseMission() {
  const oc = useOperatorCaseData()
  if (!oc || oc.mission.status !== 'produced' || !oc.mission.value?.length) {
    return (
      <p className="text-[13px] text-muted-foreground">
        No mission produced for this case yet ({oc?.mission.reason ?? 'loading'}).
      </p>
    )
  }
  const m = oc.mission.value[0]
  return (
    <div className="rounded-sm border border-border bg-background/50 p-4">
      <div className="flex flex-wrap items-center gap-2">
        <span className="text-[14px] font-semibold text-foreground">{m.mission_id}</span>
        <StatusBadge tone={statusTone(m.state)} dot>{m.state}</StatusBadge>
        <span className="font-mono text-[11px] text-muted-foreground">Case: {oc.case_id}</span>
      </div>
      <div className="mt-2 grid grid-cols-2 gap-2 sm:grid-cols-3">
        <div><div className="font-mono text-[10px] uppercase tracking-[0.1em] text-muted-foreground">Asset</div><div className="text-[13px] font-medium text-foreground">{m.asset_id ?? '—'}</div></div>
        <div><div className="font-mono text-[10px] uppercase tracking-[0.1em] text-muted-foreground">Approved By</div><div className="text-[13px] font-medium text-foreground">{m.human_approved_by ?? 'Not yet approved'}</div></div>
      </div>
    </div>
  )
}

function LiveMissionsPanel() {
  const { session, isAuthenticated, logout } = useAuth()
  const [missions, setMissions] = useState<Array<Record<string, unknown>> | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [audits, setAudits] = useState<Record<string, Array<Record<string, unknown>>>>({})
  const [authMessages, setAuthMessages] = useState<Record<string, string>>({})

  function refresh() {
    listMissions()
      .then((r) => setMissions(r.items))
      .catch((err) => setError(err instanceof Error ? err.message : 'Failed to load missions.'))
  }

  useEffect(refresh, [])

  async function loadAudit(missionId: string) {
    try {
      const r = await getMissionAudit(missionId)
      setAudits((prev) => ({ ...prev, [missionId]: r.items }))
    } catch {
      setAudits((prev) => ({ ...prev, [missionId]: [] }))
    }
  }

  async function tryApprove(missionId: string) {
    if (!isAuthenticated || !session) {
      setAuthMessages((prev) => ({ ...prev, [missionId]: 'NOT AUTHENTICATED — sign in (top right) first.' }))
      return
    }
    try {
      await approveMission(missionId, session.username)
      setAuthMessages((prev) => ({ ...prev, [missionId]: 'Authorized — confirmed by backend.' }))
      refresh()
    } catch (err) {
      if (err instanceof AuthActionError) {
        if (err.status === 401) {
          logout()
          setAuthMessages((prev) => ({ ...prev, [missionId]: 'NOT AUTHENTICATED — session invalid or expired.' }))
        } else {
          setAuthMessages((prev) => ({
            ...prev,
            [missionId]: `NOT AUTHORIZED — ${session.role} does not hold mission-approval permission.`,
          }))
        }
      } else {
        setAuthMessages((prev) => ({
          ...prev,
          [missionId]: err instanceof Error ? err.message : 'Request failed.',
        }))
      }
    }
    loadAudit(missionId)
  }

  if (error) return <p className="text-[13px] text-destructive">{error}</p>
  if (missions === null) return <p className="text-[13px] text-muted-foreground">Loading…</p>
  if (missions.length === 0) {
    return (
      <p className="text-[13px] text-muted-foreground">
        No live missions currently exist in MissionService — none has been created via the API
        in this process. This is the honest empty state, not a loading failure.
      </p>
    )
  }

  return (
    <div className="space-y-3">
      {missions.map((m) => {
        const missionId = String(m.mission_id)
        return (
          <div key={missionId} className="rounded-sm border border-border bg-background/50 p-4">
            <div className="flex flex-wrap items-center justify-between gap-2">
              <div className="flex items-center gap-2">
                <span className="text-[14px] font-semibold text-foreground">{missionId}</span>
                <StatusBadge tone={statusTone(String(m.state))} dot>{String(m.state)}</StatusBadge>
              </div>
              <div className="flex gap-2">
                <button
                  type="button"
                  onClick={() => tryApprove(missionId)}
                  className="flex items-center gap-1.5 rounded-sm border border-border bg-card px-2.5 py-1.5 text-[12px] font-medium text-foreground hover:bg-muted"
                >
                  <ShieldCheck className="h-3 w-3" />
                  Approve
                </button>
                <button
                  type="button"
                  onClick={() => loadAudit(missionId)}
                  className="flex items-center gap-1.5 rounded-sm border border-border bg-card px-2.5 py-1.5 text-[12px] font-medium text-foreground hover:bg-muted"
                >
                  <Check className="h-3 w-3" />
                  View Audit
                </button>
              </div>
            </div>
            <div className="mt-2 border-t border-border/60 pt-2">
              <MissionFsmGraph missionId={missionId} />
            </div>
            {authMessages[missionId] && (
              <p className={cn('mt-2 text-[12px]', authMessages[missionId]?.startsWith('Authorized') ? 'text-[var(--ok)]' : 'text-destructive')}>
                {authMessages[missionId]}
              </p>
            )}
            {audits[missionId] && (
              <ul className="mt-2 space-y-1 border-t border-border/60 pt-2 text-[11px] text-muted-foreground">
                {audits[missionId].length === 0 && <li>No audit entries yet.</li>}
                {audits[missionId].map((e) => (
                  <li key={String(e.audit_id)} className="font-mono">
                    {String(e.at)} — {String(e.principal_id)} ({String(e.role)}) —{' '}
                    {e.allowed ? 'ALLOWED' : 'DENIED'}
                  </li>
                ))}
              </ul>
            )}
          </div>
        )
      })}
    </div>
  )
}

function MissionsBody() {
  return (
    <>
      <div className="mb-3 flex flex-wrap items-end justify-between gap-2">
        <div>
          <h1 className="text-balance text-xl font-semibold leading-tight tracking-tight text-foreground sm:text-xl">
            Mission Control
          </h1>
          <p className="mt-0.5 font-mono text-[12px] uppercase tracking-[0.1em] text-muted-foreground">
            Active & planned missions · VARUNA
          </p>
        </div>
      </div>

      <section className="rounded-sm border border-border bg-card p-4">
        <SectionLabel>Case Mission — CASE-VALID Replay</SectionLabel>
        <div className="mt-3">
          <OperatorCaseProvider fixtureName="CASE-VALID">
            <OperatorCaseBoundary>
              <ReplayCaseMission />
            </OperatorCaseBoundary>
          </OperatorCaseProvider>
        </div>
      </section>

      <section className="mt-3 rounded-sm border border-border bg-card p-4">
        <SectionLabel>Live Missions (MissionService)</SectionLabel>
        <div className="mt-3">
          <LiveMissionsPanel />
        </div>
      </section>
    </>
  )
}

export default function MissionsPage() {
  return <MissionsBody />
}
