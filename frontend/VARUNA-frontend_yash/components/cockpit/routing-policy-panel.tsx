'use client'

/**
 * Static alert-routing hierarchy reference (Phase 0c/2b). Answers "who gets
 * told what, and why" BEFORE any alert fires — not reconstructable only
 * after the fact from one alert's own `routing` field. Every row is the
 * real, deterministic `varuna_alerts.routing_policy.route()` output.
 */
import { useEffect, useState } from 'react'
import { Card } from '@/components/cockpit/cockpit-panels'
import { StatusBadge } from '@/components/primitives'
import { getRoutingPolicy, type RoutingPolicyRow } from '@/lib/api'

const SEVERITY_TONE: Record<string, 'ok' | 'warn' | 'destructive'> = {
  low: 'ok', medium: 'warn', high: 'warn', critical: 'destructive',
}

export function RoutingPolicyPanel() {
  const [rows, setRows] = useState<RoutingPolicyRow[]>([])
  const [error, setError] = useState<string | null>(null)
  const [dimension, setDimension] = useState<string>('')

  useEffect(() => {
    getRoutingPolicy()
      .then((r) => setRows(r.items))
      .catch((e) => setError(e instanceof Error ? e.message : 'Failed to load routing policy'))
  }, [])

  if (error) {
    return (
      <Card title="Alert Routing Hierarchy">
        <p className="text-[12px] text-destructive">{error}</p>
      </Card>
    )
  }

  const dimensions = Array.from(new Set(rows.map((r) => r.dimension)))
  const visible = dimension ? rows.filter((r) => r.dimension === dimension) : rows

  return (
    <Card
      title="Alert Routing Hierarchy"
      right={
        <select
          value={dimension}
          onChange={(e) => setDimension(e.target.value)}
          className="rounded-sm border border-border bg-background px-2 py-1 font-mono text-[10px] text-foreground"
        >
          <option value="">all dimensions</option>
          {dimensions.map((d) => <option key={d} value={d}>{d}</option>)}
        </select>
      }
    >
      <p className="mb-2 text-[11px] text-muted-foreground">
        Deterministic, policy-driven — not "notify everyone." A dimension
        that matches no specific rule routes to the Duty Officer only.
      </p>
      <div className="overflow-x-auto">
        <table className="w-full border-collapse font-mono text-[11px]">
          <thead>
            <tr className="border-b border-border text-left text-muted-foreground">
              <th className="py-1 pr-3 font-medium">Dimension</th>
              <th className="py-1 pr-3 font-medium">Severity</th>
              <th className="py-1 pr-3 font-medium">Routed to</th>
              <th className="py-1 font-medium">Reason</th>
            </tr>
          </thead>
          <tbody>
            {visible.map((row, i) => (
              <tr key={i} className="border-b border-border/50 align-top">
                <td className="py-1.5 pr-3 text-foreground">{row.dimension}</td>
                <td className="py-1.5 pr-3">
                  <StatusBadge tone={SEVERITY_TONE[row.severity] ?? 'ok'}>{row.severity}</StatusBadge>
                </td>
                <td className="py-1.5 pr-3">
                  <div className="flex flex-wrap gap-1">
                    {row.recipients.map((rec) => (
                      <span
                        key={rec.role}
                        className="rounded-sm border border-border bg-muted/40 px-1.5 py-0.5 text-[10px]"
                        title={rec.rbac_role ? `RBAC: ${rec.rbac_role}` : 'external stakeholder — no API permissions'}
                      >
                        {rec.title}
                      </span>
                    ))}
                  </div>
                </td>
                <td className="py-1.5 text-muted-foreground">{row.reason}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </Card>
  )
}
