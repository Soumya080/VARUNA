'use client'

/**
 * Alert Center — the operational surface for Workstream A.
 * Shows what the backend actually produced: severity plus its basis, the
 * material dimension that changed, the routing decision and who it reached,
 * per-channel delivery with honest REAL/SIMULATED/NOT_CONFIGURED modes, the
 * full transition history, and the lifecycle actions.
 */
import { useState } from 'react'
import { StatusBadge } from '@/components/primitives'
import { Card, Row } from './cockpit-panels'
import { cn } from '@/lib/utils'
import type { AlertLifecycleRecord } from '@/lib/api'

export function severityTone(sev: string) {
  if (sev === 'critical' || sev === 'high') return 'destructive' as const
  if (sev === 'medium' || sev === 'warning') return 'warn' as const
  if (sev === 'blocked') return 'muted' as const
  return 'ok' as const
}

function lifecycleTone(s: string) {
  if (s === 'resolved') return 'ok' as const
  if (s === 'escalated') return 'destructive' as const
  if (s === 'acknowledged') return 'warn' as const
  return 'muted' as const
}

function deliveryTone(mode: string) {
  if (mode === 'REAL') return 'ok' as const
  if (mode === 'SIMULATED') return 'saffron' as const
  return 'muted' as const
}

export function AlertCenter({
  alerts,
  channels,
  onAction,
  busy,
}: {
  alerts: AlertLifecycleRecord[]
  channels: Record<string, string>
  onAction: (
    alertId: string,
    action: 'acknowledge' | 'escalate' | 'resolve',
    label: string,
  ) => void
  busy: boolean
}) {
  const [openId, setOpenId] = useState<string | null>(null)

  return (
    <Card
      title={`Alert Center (${alerts.length})`}
      id="alert-center"
      right={
        <div className="flex flex-wrap items-center gap-1">
          {Object.entries(channels).map(([ch, mode]) => (
            <StatusBadge key={ch} tone={deliveryTone(mode)}>
              {ch}: {mode}
            </StatusBadge>
          ))}
        </div>
      }
    >
      {alerts.length === 0 && (
        <p className="text-[12px] text-muted-foreground">
          No alerts for this case. For a fail-closed case this is the correct outcome — the
          Material Change Engine found nothing an operator should act on, and no alert is
          fabricated.
        </p>
      )}

      <div className="space-y-2">
        {alerts.map((a) => {
          const open = openId === a.alert_id
          const next: Array<['acknowledge' | 'escalate' | 'resolve', string]> =
            a.status === 'resolved'
              ? []
              : a.status === 'escalated'
                ? [['resolve', 'Resolve']]
                : a.status === 'acknowledged'
                  ? [
                      ['escalate', 'Escalate'],
                      ['resolve', 'Resolve'],
                    ]
                  : [
                      ['acknowledge', 'Acknowledge'],
                      ['escalate', 'Escalate'],
                    ]

          return (
            <div
              key={a.alert_id}
              className="rounded-sm border border-border bg-background/50 p-2.5"
            >
              <div className="flex flex-wrap items-center gap-1.5">
                <StatusBadge tone={severityTone(a.severity)}>{a.severity}</StatusBadge>
                <StatusBadge tone={lifecycleTone(a.status)} dot>
                  {a.status.replace(/_/g, ' ')}
                </StatusBadge>
                <span className="font-mono text-[11px] text-foreground">
                  {a.material_dimension ?? a.event_type}
                </span>
                {a.is_simulated && <StatusBadge tone="saffron">SIMULATED</StatusBadge>}
                <button
                  type="button"
                  onClick={() => setOpenId(open ? null : a.alert_id)}
                  className="ml-auto font-mono text-[10px] uppercase tracking-[0.08em] text-muted-foreground hover:text-foreground"
                >
                  {open ? 'Hide detail' : 'Detail'}
                </button>
              </div>

              <p className="mt-1 text-[12px] leading-snug text-muted-foreground">{a.reason}</p>

              {a.routing && (
                <div className="mt-1 flex flex-wrap items-center gap-1">
                  <span className="font-mono text-[10px] uppercase tracking-[0.1em] text-muted-foreground">
                    Routed to
                  </span>
                  {a.routing.recipients.map((r) => (
                    <StatusBadge key={r.role} tone="muted">
                      {r.role.replace(/_/g, ' ')}
                    </StatusBadge>
                  ))}
                </div>
              )}

              {open && (
                <div className="mt-2 space-y-2 border-t border-border pt-2">
                  <Row label="Severity basis" value={a.severity_basis ?? '—'} />
                  <Row label="Routing rule" value={a.routing?.matched_rule ?? '—'} />
                  <Row label="Engine mode" value={a.engine_mode ?? '—'} />

                  <div>
                    <div className="font-mono text-[10px] uppercase tracking-[0.1em] text-muted-foreground">
                      Notification delivery
                    </div>
                    <ul className="mt-1 space-y-0.5">
                      {a.deliveries.map((d) => (
                        <li key={d.delivery_id} className="flex items-center gap-1.5 text-[11px]">
                          <StatusBadge tone={deliveryTone(d.mode)}>{d.mode}</StatusBadge>
                          <span className="font-mono text-foreground">{d.channel}</span>
                          <span className="text-muted-foreground">
                            &rarr; {d.recipient_role}
                          </span>
                          <span className="ml-auto font-mono text-muted-foreground">
                            {d.status}
                          </span>
                        </li>
                      ))}
                    </ul>
                  </div>

                  <div>
                    <div className="font-mono text-[10px] uppercase tracking-[0.1em] text-muted-foreground">
                      Transition history (audited)
                    </div>
                    <ol className="mt-1 space-y-0.5">
                      {a.transitions.map((t, i) => (
                        <li key={i} className="font-mono text-[10px] text-muted-foreground">
                          {t.from} &rarr; <span className="text-foreground">{t.to}</span> ·{' '}
                          {t.actor}
                        </li>
                      ))}
                    </ol>
                  </div>
                </div>
              )}

              <div className="mt-2 flex flex-wrap gap-1.5">
                {next.map(([action, label]) => (
                  <button
                    key={action}
                    type="button"
                    disabled={busy}
                    onClick={() => onAction(a.alert_id, action, label)}
                    className={cn(
                      'rounded-sm border border-border bg-card px-2 py-1 text-[11px] font-medium hover:bg-muted disabled:opacity-40',
                    )}
                  >
                    {label}
                  </button>
                ))}
                {next.length === 0 && (
                  <span className="text-[11px] text-muted-foreground">
                    Resolved — no further action.
                  </span>
                )}
              </div>
            </div>
          )
        })}
      </div>
    </Card>
  )
}
