'use client'

/**
 * Alert Center — global, backed by GET /v1/alerts.
 *
 * Previously pinned to the single hardcoded case 'REPLAY-CASE-VALID', because
 * no global alert endpoint existed. It now shows every alert with real
 * severity/status filters and honest per-channel delivery.
 *
 * Reuses the cockpit's AlertCenter component so the two surfaces are visually
 * and behaviourally identical — one alert vocabulary, not two.
 */
import { useCallback, useEffect, useState } from 'react'
import { AlertCenter } from '@/components/cockpit/alert-center'
import { Card } from '@/components/cockpit/cockpit-panels'
import { NotificationTestPanel } from '@/components/cockpit/notification-test-panel'
import { RoutingPolicyPanel } from '@/components/cockpit/routing-policy-panel'
import { StatusBadge } from '@/components/primitives'
import { useAuth } from '@/lib/auth-context'
import {
  acknowledgeAlert, AuthActionError, escalateAlert, getOperationalSummary,
  listAlerts, resolveAlert, type AlertLifecycleRecord,
} from '@/lib/api'
import { cn } from '@/lib/utils'
import { RefreshCw } from 'lucide-react'

const SEVERITIES = ['critical', 'high', 'medium', 'low', 'warning', 'info'] as const
const STATUSES = [
  'created', 'routed', 'delivery_pending', 'delivered',
  'acknowledged', 'escalated', 'resolved',
] as const

export default function AlertsPage() {
  const { session, isAuthenticated, logout } = useAuth()
  const [alerts, setAlerts] = useState<AlertLifecycleRecord[]>([])
  const [total, setTotal] = useState(0)
  const [channels, setChannels] = useState<Record<string, string>>({})
  const [severity, setSeverity] = useState<string>('')
  const [status, setStatus] = useState<string>('')
  const [busy, setBusy] = useState(false)
  const [msg, setMsg] = useState<{ text: string; ok: boolean } | null>(null)
  const [error, setError] = useState<string | null>(null)

  const load = useCallback(async () => {
    setError(null)
    try {
      const r = await listAlerts({ severity, status, limit: 200 })
      setAlerts(r.items)
      setTotal(r.total)
    } catch (e) {
      setAlerts([])
      setError(e instanceof Error ? e.message : 'Failed to load alerts')
    }
    // Channel configuration is global; any case surfaces the same report.
    try {
      const first = await listAlerts({ limit: 1 })
      if (first.items.length) {
        setChannels((await getOperationalSummary(first.items[0].case_id)).channels)
      }
    } catch {
      setChannels({})
    }
  }, [severity, status])

  useEffect(() => {
    load()
  }, [load])

  async function onAction(
    alertId: string,
    action: 'acknowledge' | 'escalate' | 'resolve',
    label: string,
  ) {
    setMsg(null)
    if (!isAuthenticated) {
      setMsg({ text: 'NOT AUTHENTICATED — sign in (top right) first.', ok: false })
      return
    }
    const fn = action === 'acknowledge' ? acknowledgeAlert
      : action === 'escalate' ? escalateAlert : resolveAlert
    setBusy(true)
    try {
      await fn(alertId)
      setMsg({ text: `${label} confirmed by backend.`, ok: true })
      await load()
    } catch (e) {
      if (e instanceof AuthActionError) {
        if (e.status === 401) {
          logout()
          setMsg({ text: 'NOT AUTHENTICATED — session expired.', ok: false })
        } else {
          setMsg({
            text: `NOT AUTHORIZED — ${session?.role ?? 'your role'} cannot ${action} alerts.`,
            ok: false,
          })
        }
      } else {
        setMsg({ text: e instanceof Error ? e.message : 'Action failed.', ok: false })
      }
    } finally {
      setBusy(false)
    }
  }

  const counts = SEVERITIES.map((s) => ({
    sev: s, n: alerts.filter((a) => a.severity === s).length,
  })).filter((c) => c.n > 0)

  return (
    <>
      <div className="mb-3 flex flex-wrap items-end justify-between gap-2">
        <div>
          <h1 className="text-balance text-xl font-semibold leading-tight tracking-tight text-foreground">
            Alert Center
          </h1>
          <p className="mt-0.5 font-mono text-[12px] uppercase tracking-[0.1em] text-muted-foreground">
            {total} alert{total === 1 ? '' : 's'} across all cases · live from backend
          </p>
        </div>
        <button
          type="button"
          onClick={load}
          className="flex items-center gap-1.5 rounded-sm border border-border bg-card px-3 py-1.5 text-[12px] font-semibold uppercase tracking-[0.08em] text-muted-foreground hover:bg-muted"
        >
          <RefreshCw className="h-3.5 w-3.5" /> Refresh
        </button>
      </div>

      {counts.length > 0 && (
        <div className="mb-3 flex flex-wrap items-center gap-1.5">
          {counts.map(({ sev, n }) => (
            <StatusBadge
              key={sev}
              tone={sev === 'critical' || sev === 'high' ? 'destructive'
                : sev === 'medium' || sev === 'warning' ? 'warn' : 'ok'}
            >
              {sev}: {n}
            </StatusBadge>
          ))}
        </div>
      )}

      <Card title="Filters">
        <div className="flex flex-wrap items-center gap-3">
          <label className="flex items-center gap-1.5">
            <span className="font-mono text-[10px] uppercase tracking-[0.1em] text-muted-foreground">
              Severity
            </span>
            <select
              value={severity}
              onChange={(e) => setSeverity(e.target.value)}
              className="rounded-sm border border-border bg-background px-2 py-1 font-mono text-[11px] text-foreground"
            >
              <option value="">all</option>
              {SEVERITIES.map((s) => <option key={s} value={s}>{s}</option>)}
            </select>
          </label>
          <label className="flex items-center gap-1.5">
            <span className="font-mono text-[10px] uppercase tracking-[0.1em] text-muted-foreground">
              Status
            </span>
            <select
              value={status}
              onChange={(e) => setStatus(e.target.value)}
              className="rounded-sm border border-border bg-background px-2 py-1 font-mono text-[11px] text-foreground"
            >
              <option value="">all</option>
              {STATUSES.map((s) => <option key={s} value={s}>{s.replace(/_/g, ' ')}</option>)}
            </select>
          </label>
          {(severity || status) && (
            <button
              type="button"
              onClick={() => { setSeverity(''); setStatus('') }}
              className="font-mono text-[10px] uppercase tracking-[0.08em] text-muted-foreground hover:text-foreground"
            >
              Clear filters
            </button>
          )}
        </div>
      </Card>

      {msg && (
        <p
          className={cn(
            'my-3 rounded-sm border px-3 py-2 text-[12px]',
            msg.ok
              ? 'border-[color-mix(in_oklch,var(--ok)_40%,transparent)] bg-[color-mix(in_oklch,var(--ok)_8%,transparent)] text-[color-mix(in_oklch,var(--ok)_55%,black)]'
              : 'border-destructive/40 bg-destructive/5 text-destructive',
          )}
        >
          {msg.text}
        </p>
      )}
      {error && (
        <p className="my-3 rounded-sm border border-destructive/40 bg-destructive/5 px-3 py-2 text-[12px] text-destructive">
          {error}
        </p>
      )}

      <div className="mt-3">
        <AlertCenter alerts={alerts} channels={channels} onAction={onAction} busy={busy} />
      </div>

      <div className="mt-3">
        <RoutingPolicyPanel />
      </div>

      <div className="mt-3">
        <NotificationTestPanel isAdmin={session?.role === 'admin'} />
      </div>
    </>
  )
}
