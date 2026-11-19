'use client'

/**
 * Admin-only credential-verification panel (Phase 0b).
 *
 * Answers "how does anybody actually get an alert" concretely: fires a REAL,
 * clearly test-marked notification through POST /v1/alerts/test-notification
 * and renders exactly what each channel reported. A NOT_CONFIGURED result is
 * shown as honestly as a SENT one — this panel never implies success that
 * didn't happen. See docs/product/ALERT_CHANNEL_SETUP.md for how to turn
 * NOT_CONFIGURED into REAL (it's an .env configuration step, not a code gap).
 */
import { useState } from 'react'
import { Card, Row } from '@/components/cockpit/cockpit-panels'
import { StatusBadge } from '@/components/primitives'
import { AuthActionError, testNotification, type TestNotificationResult } from '@/lib/api'

const ROLES = ['duty_officer', 'supervisor', 'field_operator', 'enforcement', 'dg_shipping', 'state_pcb']
const CHANNELS = ['email', 'sms'] as const

function toneFor(status: string) {
  if (status === 'SENT' || status === 'DELIVERED') return 'ok' as const
  if (status === 'FAILED') return 'destructive' as const
  return 'muted' as const
}

export function NotificationTestPanel({ isAdmin }: { isAdmin: boolean }) {
  const [role, setRole] = useState('duty_officer')
  const [channels, setChannels] = useState<string[]>(['email', 'sms'])
  const [busy, setBusy] = useState(false)
  const [result, setResult] = useState<TestNotificationResult | null>(null)
  const [error, setError] = useState<string | null>(null)

  if (!isAdmin) {
    return (
      <Card title="Notification Test">
        <p className="text-[12px] text-muted-foreground">
          Sign in as an admin to verify SMS/email credentials from here.
        </p>
      </Card>
    )
  }

  function toggleChannel(ch: string) {
    setChannels((prev) => (prev.includes(ch) ? prev.filter((c) => c !== ch) : [...prev, ch]))
  }

  async function send() {
    setBusy(true)
    setError(null)
    setResult(null)
    try {
      const r = await testNotification(role, channels.length ? channels : undefined)
      setResult(r)
    } catch (e) {
      if (e instanceof AuthActionError) {
        setError(e.status === 403
          ? 'NOT AUTHORIZED — this account cannot send test notifications.'
          : 'NOT AUTHENTICATED — sign in again.')
      } else {
        setError(e instanceof Error ? e.message : 'Test failed.')
      }
    } finally {
      setBusy(false)
    }
  }

  return (
    <Card title="Notification Test" right={<StatusBadge tone="navy">admin only</StatusBadge>}>
      <div className="flex flex-wrap items-center gap-3">
        <label className="flex items-center gap-1.5">
          <span className="font-mono text-[10px] uppercase tracking-[0.1em] text-muted-foreground">
            Role
          </span>
          <select
            value={role}
            onChange={(e) => setRole(e.target.value)}
            className="rounded-sm border border-border bg-background px-2 py-1 font-mono text-[11px] text-foreground"
          >
            {ROLES.map((r) => <option key={r} value={r}>{r}</option>)}
          </select>
        </label>
        {CHANNELS.map((ch) => (
          <label key={ch} className="flex items-center gap-1.5 font-mono text-[11px]">
            <input
              type="checkbox"
              checked={channels.includes(ch)}
              onChange={() => toggleChannel(ch)}
            />
            {ch}
          </label>
        ))}
        <button
          type="button"
          onClick={send}
          disabled={busy}
          className="rounded-sm border border-border bg-primary px-3 py-1 font-mono text-[11px] font-semibold uppercase tracking-[0.08em] text-primary-foreground disabled:opacity-50"
        >
          {busy ? 'Sending…' : 'Send test'}
        </button>
      </div>

      {error && (
        <p className="mt-2 rounded-sm border border-destructive/40 bg-destructive/5 px-2 py-1.5 text-[12px] text-destructive">
          {error}
        </p>
      )}

      {result && (
        <div className="mt-3 space-y-2">
          <Row label="Configuration snapshot" value="" />
          {Object.entries(result.channels).map(([ch, mode]) => (
            <Row
              key={ch}
              label={ch}
              value={<StatusBadge tone={mode === 'REAL' ? 'ok' : mode === 'SIMULATED' ? 'warn' : 'muted'}>{mode}</StatusBadge>}
            />
          ))}
          <div className="mt-2 border-t border-border pt-2">
            <span className="font-mono text-[10px] uppercase tracking-[0.1em] text-muted-foreground">
              This attempt
            </span>
            {result.results.map((d) => (
              <Row
                key={d.delivery_id}
                label={`${d.channel} → ${d.recipient_role}`}
                value={
                  <span className="flex items-center gap-1.5">
                    <StatusBadge tone={toneFor(d.status)}>{d.status}</StatusBadge>
                    {d.error && <span className="text-destructive">{d.error}</span>}
                  </span>
                }
              />
            ))}
          </div>
          {result.results.some((d) => d.status === 'NOT_CONFIGURED') && (
            <p className="mt-1 text-[11px] text-muted-foreground">
              NOT_CONFIGURED means the send code is real but credentials are
              missing from .env — see docs/product/ALERT_CHANNEL_SETUP.md.
            </p>
          )}
        </div>
      )}
    </Card>
  )
}
