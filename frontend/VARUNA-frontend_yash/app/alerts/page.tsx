'use client'

import { useEffect, useState } from 'react'
import { SectionLabel, StatusBadge } from '@/components/primitives'
import { EvidenceModeBadge } from '@/components/evidence-mode-badge'
import type { EvidenceModeValue } from '@/lib/operator-case-types'
import { OperatorCaseProvider, useOperatorCaseData } from '@/lib/operator-case-context'
import { OperatorCaseBoundary } from '@/components/operator-case-boundary'
import { useAuth } from '@/lib/auth-context'
import {
  acknowledgeAlert,
  AuthActionError,
  escalateAlert,
  getCaseAlerts,
  resolveAlert,
  type AlertLifecycleRecord,
} from '@/lib/api'
import { AlertTriangle, Bell, Check } from 'lucide-react'
import { cn } from '@/lib/utils'

/**
 * STEP 6: replaces the previous fully-hardcoded 9-entry mock (`ALT-2471`,
 * "AIS transponder gap...", etc. — see docs/product/
 * ALERT_OPERATIONAL_DIAGNOSTIC.md item 17). Every alert shown here now
 * comes from `GET /v1/cases/{case_id}/alerts` — the STEP 6 lifecycle
 * layer correlated from the same `GoldenCaseWorkflow` run the rest of the
 * operator cockpit reads (`OperatorCase.alerts` shows the same underlying
 * delivery; this page adds the lifecycle status and the actions to change
 * it). CASE-VALID is the same replay case the rest of the app defaults to.
 */
const REPLAY_CASE_ID = 'REPLAY-CASE-VALID'

function severityTone(sev: string) {
  if (sev === 'critical') return 'destructive' as const
  if (sev === 'warning') return 'warn' as const
  if (sev === 'blocked') return 'muted' as const
  return 'ok' as const
}

function lifecycleTone(status: string) {
  if (status === 'resolved') return 'ok' as const
  if (status === 'escalated') return 'destructive' as const
  if (status === 'acknowledged') return 'warn' as const
  return 'muted' as const
}

function AlertActions({
  alert,
  onChanged,
}: {
  alert: AlertLifecycleRecord
  onChanged: (updated: AlertLifecycleRecord) => void
}) {
  const { isAuthenticated, logout } = useAuth()
  const [statusMsg, setStatusMsg] = useState<{ text: string; kind: 'error' | 'success' } | null>(null)
  const [pending, setPending] = useState(false)

  async function run(action: (id: string) => Promise<AlertLifecycleRecord>, label: string) {
    setPending(true)
    setStatusMsg(null)
    try {
      const updated = await action(alert.alert_id)
      onChanged(updated)
      setStatusMsg({ text: `${label} confirmed by backend.`, kind: 'success' })
    } catch (err) {
      if (err instanceof AuthActionError) {
        if (err.status === 401) {
          logout() // stored token is invalid/expired — clear it, force re-login
          setStatusMsg({ text: 'NOT AUTHENTICATED — please sign in.', kind: 'error' })
        } else {
          setStatusMsg({ text: 'NOT AUTHORIZED for this action with your current role.', kind: 'error' })
        }
      } else {
        setStatusMsg({ text: err instanceof Error ? err.message : 'Action failed.', kind: 'error' })
      }
    } finally {
      setPending(false)
    }
  }

  if (!isAuthenticated) {
    return <p className="mt-2 text-[12px] text-muted-foreground">Sign in (top right) to act on this alert.</p>
  }

  const nextActions: Array<{ label: string; fn: typeof acknowledgeAlert }> =
    alert.status === 'created'
      ? [
          { label: 'Acknowledge', fn: acknowledgeAlert },
          { label: 'Escalate', fn: escalateAlert },
        ]
      : alert.status === 'acknowledged'
        ? [
            { label: 'Escalate', fn: escalateAlert },
            { label: 'Resolve', fn: resolveAlert },
          ]
        : alert.status === 'escalated'
          ? [{ label: 'Resolve', fn: resolveAlert }]
          : []

  return (
    <div className="mt-2 flex flex-wrap items-center gap-2">
      {nextActions.map((a) => (
        <button
          key={a.label}
          type="button"
          disabled={pending}
          onClick={() => run(a.fn, a.label)}
          className="flex items-center gap-1.5 rounded-sm border border-border bg-card px-2.5 py-1.5 text-[12px] font-medium text-foreground hover:bg-muted disabled:opacity-50"
        >
          <Check className="h-3 w-3" />
          {a.label}
        </button>
      ))}
      {nextActions.length === 0 && (
        <span className="text-[12px] text-muted-foreground">No further action — resolved.</span>
      )}
      {statusMsg && (
        <span className={cn('text-[12px]', statusMsg.kind === 'success' ? 'text-[var(--ok)]' : 'text-destructive')}>
          {statusMsg.text}
        </span>
      )}
    </div>
  )
}

function AlertCenterBody() {
  const oc = useOperatorCaseData()
  const [alerts, setAlerts] = useState<AlertLifecycleRecord[] | null>(null)
  const [loadError, setLoadError] = useState<string | null>(null)

  useEffect(() => {
    let cancelled = false
    getCaseAlerts(REPLAY_CASE_ID)
      .then((r) => {
        if (!cancelled) setAlerts(r.items)
      })
      .catch((err) => {
        if (!cancelled) setLoadError(err instanceof Error ? err.message : 'Failed to load alerts.')
      })
    return () => {
      cancelled = true
    }
  }, [])

  function applyUpdate(updated: AlertLifecycleRecord) {
    setAlerts((prev) => (prev ? prev.map((a) => (a.alert_id === updated.alert_id ? updated : a)) : prev))
  }

  const counts = {
    critical: alerts?.filter((a) => a.severity === 'critical').length ?? 0,
    warning: alerts?.filter((a) => a.severity === 'warning').length ?? 0,
    info: alerts?.filter((a) => a.severity === 'info').length ?? 0,
  }

  return (
    <>
      <div className="mb-3 flex flex-wrap items-end justify-between gap-2">
        <div>
          <h1 className="text-balance text-xl font-semibold leading-tight tracking-tight text-foreground sm:text-xl">
            Alert Center
          </h1>
          <p className="mt-0.5 font-mono text-[12px] uppercase tracking-[0.1em] text-muted-foreground">
            {REPLAY_CASE_ID} · engine_mode={oc?.system_status.engine_mode ?? 'unknown'}
          </p>
        </div>
      </div>

      <div className="grid grid-cols-3 gap-3 sm:grid-cols-3">
        {[
          { label: 'Critical', count: counts.critical, tone: 'destructive', icon: AlertTriangle },
          { label: 'Warning', count: counts.warning, tone: 'warn', icon: Bell },
          { label: 'Informational', count: counts.info, tone: 'muted', icon: Bell },
        ].map((s) => (
          <div key={s.label} className="rounded-sm border border-border bg-card p-3">
            <div className="flex items-center gap-2">
              <s.icon className={cn('h-4 w-4', s.tone === 'destructive' ? 'text-destructive' : s.tone === 'warn' ? 'text-[var(--warn)]' : 'text-muted-foreground')} />
              <span className="font-mono text-[10px] uppercase tracking-[0.12em] text-muted-foreground">{s.label}</span>
            </div>
            <div className="mt-1 font-mono text-[23px] font-bold text-foreground">{s.count}</div>
          </div>
        ))}
      </div>

      <div className="mt-3 space-y-2">
        {loadError && (
          <p className="rounded-sm border border-destructive/40 bg-destructive/5 p-3 text-[13px] text-destructive">
            {loadError}
          </p>
        )}
        {alerts !== null && alerts.length === 0 && !loadError && (
          <p className="rounded-sm border border-border bg-card p-4 text-[13px] text-muted-foreground">
            No material alerts for this case. This is the honest state — CASE-VALID's validity
            gate produced exactly one alert candidate, and it may already be resolved above, or
            none has been generated yet if the replay case has not been fetched.
          </p>
        )}
        {alerts?.map((alert) => (
          <section key={alert.alert_id} className="rounded-sm border border-border bg-card p-4">
            <div className="flex items-start gap-3">
              <AlertTriangle
                className={cn(
                  'h-4 w-4 shrink-0 mt-0.5',
                  alert.severity === 'critical' ? 'text-destructive' : alert.severity === 'warning' ? 'text-[var(--warn)]' : 'text-muted-foreground',
                )}
              />
              <div className="min-w-0 flex-1">
                <div className="flex flex-wrap items-center gap-2">
                  <span className="text-[14px] font-semibold text-foreground">{alert.event_type}</span>
                  <StatusBadge tone={severityTone(alert.severity)}>{alert.severity}</StatusBadge>
                  <StatusBadge tone={lifecycleTone(alert.status)} dot>{alert.status}</StatusBadge>
                  {alert.evidence_mode && (
                    <EvidenceModeBadge mode={alert.evidence_mode as EvidenceModeValue} compact />
                  )}
                </div>
                <p className="mt-1 text-[13px] text-muted-foreground">{alert.reason}</p>
                <div className="mt-2 flex flex-wrap items-center gap-4 text-[12px] text-muted-foreground">
                  <span>Case: {alert.case_id}</span>
                  <span>Created: {new Date(alert.created_at).toISOString()}</span>
                  <span className="font-mono text-[11px]">{alert.alert_id}</span>
                </div>
                {(alert.acknowledged_by || alert.escalated_by || alert.resolved_by) && (
                  <div className="mt-1 text-[11px] text-muted-foreground">
                    {alert.acknowledged_by && <span>Acknowledged by {alert.acknowledged_by}. </span>}
                    {alert.escalated_by && <span>Escalated by {alert.escalated_by}. </span>}
                    {alert.resolved_by && <span>Resolved by {alert.resolved_by}.</span>}
                  </div>
                )}
                <AlertActions alert={alert} onChanged={applyUpdate} />
              </div>
            </div>
          </section>
        ))}
      </div>
    </>
  )
}

export default function AlertsPage() {
  return (
    <OperatorCaseProvider fixtureName="CASE-VALID">
      <OperatorCaseBoundary>
        <AlertCenterBody />
      </OperatorCaseBoundary>
    </OperatorCaseProvider>
  )
}
