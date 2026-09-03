'use client'

/**
 * Cases — real, backed by GET /v1/cases.
 *
 * Replaces a fully mock page whose "New Case" button had no handler at all,
 * whose "search" was a <div> pretending to be an input, and whose every row
 * navigated to `/` regardless of which case was clicked.
 *
 * Uses the same Card/Row/StatusBadge vocabulary as the cockpit so the app
 * reads as one product.
 */
import { useCallback, useEffect, useMemo, useState } from 'react'
import Link from 'next/link'
import { Card, Row } from '@/components/cockpit/cockpit-panels'
import { StatusBadge } from '@/components/primitives'
import { EngineModeBadge } from '@/components/evidence-mode-badge'
import { useAuth } from '@/lib/auth-context'
import {
  AuthActionError, createCase, listCases, type CaseIntakeDetail, type CaseRow,
} from '@/lib/api'
import { cn } from '@/lib/utils'
import { ChevronDown, ChevronRight, FilePlus2, RefreshCw, Search } from 'lucide-react'

function statusTone(s: string) {
  if (s === 'complete') return 'ok' as const
  if (s === 'ood' || s === 'blocked' || s === 'failed') return 'destructive' as const
  if (s === 'unavailable') return 'muted' as const
  return 'warn' as const
}

function validityTone(v: string | null) {
  if (v === 'valid') return 'ok' as const
  if (v === 'degraded') return 'warn' as const
  if (v === 'restricted' || v === 'inconclusive') return 'destructive' as const
  return 'muted' as const
}

export default function CasesPage() {
  const { session, isAuthenticated, logout } = useAuth()
  const [cases, setCases] = useState<CaseRow[] | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [query, setQuery] = useState('')
  const [busy, setBusy] = useState(false)
  const [msg, setMsg] = useState<{ text: string; ok: boolean } | null>(null)
  const [showDetails, setShowDetails] = useState(false)
  const [detail, setDetail] = useState({
    reportedBy: '', lon: '', lat: '', observationSource: '', priority: '', notes: '',
  })

  const load = useCallback(async () => {
    setError(null)
    try {
      setCases((await listCases()).items)
    } catch (e) {
      setCases([])
      setError(e instanceof Error ? e.message : 'Failed to load cases')
    }
  }, [])

  useEffect(() => {
    load()
  }, [load])

  const filtered = useMemo(() => {
    if (!cases) return []
    const q = query.trim().toLowerCase()
    if (!q) return cases
    return cases.filter((c) =>
      [c.case_id, c.status, c.validity_state, c.recommendation, c.engine_mode]
        .some((f) => (f ?? '').toLowerCase().includes(q)),
    )
  }, [cases, query])

  async function handleNewCase(withDetail?: CaseIntakeDetail) {
    setMsg(null)
    if (!isAuthenticated) {
      setMsg({ text: 'NOT AUTHENTICATED — sign in (top right) to create a case.', ok: false })
      return
    }
    setBusy(true)
    try {
      const created = await createCase(undefined, withDetail)
      setMsg({ text: `Case ${created.case_id} created — confirmed by backend.`, ok: true })
      setShowDetails(false)
      setDetail({ reportedBy: '', lon: '', lat: '', observationSource: '', priority: '', notes: '' })
      await load()
    } catch (e) {
      if (e instanceof AuthActionError) {
        if (e.status === 401) {
          logout()
          setMsg({ text: 'NOT AUTHENTICATED — session expired.', ok: false })
        } else {
          setMsg({
            text: `NOT AUTHORIZED — ${session?.role ?? 'your role'} lacks CREATE_CASE.`,
            ok: false,
          })
        }
      } else {
        setMsg({ text: e instanceof Error ? e.message : 'Create failed.', ok: false })
      }
    } finally {
      setBusy(false)
    }
  }

  function handleCreateWithDetails() {
    const lon = parseFloat(detail.lon)
    const lat = parseFloat(detail.lat)
    const hasLocation = detail.lon.trim() !== '' && detail.lat.trim() !== '' && !Number.isNaN(lon) && !Number.isNaN(lat)
    handleNewCase({
      reported_by: detail.reportedBy.trim() || undefined,
      initial_location: hasLocation ? { lon, lat } : undefined,
      observation_source: detail.observationSource.trim() || undefined,
      priority: detail.priority.trim() || undefined,
      notes: detail.notes.trim() || undefined,
    })
  }

  return (
    <>
      <div className="mb-3 flex flex-wrap items-end justify-between gap-2">
        <div>
          <h1 className="text-balance text-xl font-semibold leading-tight tracking-tight text-foreground">
            Cases
          </h1>
          <p className="mt-0.5 font-mono text-[12px] uppercase tracking-[0.1em] text-muted-foreground">
            {cases === null ? 'Loading…' : `${cases.length} case${cases.length === 1 ? '' : 's'} · live from backend`}
          </p>
        </div>
        <div className="flex flex-wrap items-center gap-2">
          <button
            type="button"
            onClick={load}
            className="flex items-center gap-1.5 rounded-sm border border-border bg-card px-3 py-1.5 text-[12px] font-semibold uppercase tracking-[0.08em] text-muted-foreground hover:bg-muted"
          >
            <RefreshCw className="h-3.5 w-3.5" /> Refresh
          </button>
          <button
            type="button"
            disabled={busy}
            onClick={() => handleNewCase()}
            title={isAuthenticated
              ? 'Calls POST /v1/cases with your JWT. No details required.'
              : 'Sign in first — case creation is RBAC-gated.'}
            className="flex items-center gap-1.5 rounded-sm bg-primary px-3 py-1.5 text-[12px] font-semibold uppercase tracking-[0.08em] text-primary-foreground hover:bg-[var(--navy-muted)] disabled:opacity-40"
          >
            <FilePlus2 className="h-3.5 w-3.5" />
            {busy ? 'Creating…' : 'Create case now (no details)'}
          </button>
          <button
            type="button"
            onClick={() => setShowDetails((v) => !v)}
            className="flex items-center gap-1 font-mono text-[11px] uppercase tracking-[0.08em] text-muted-foreground hover:text-foreground"
          >
            {showDetails ? <ChevronDown className="h-3 w-3" /> : <ChevronRight className="h-3 w-3" />}
            Add details
          </button>
        </div>
      </div>

      {showDetails && (
        <Card title="Case intake detail (optional)">
          <p className="mb-2 text-[12px] text-muted-foreground">
            Every field below is optional — supply what you have. Nothing is
            inferred or fabricated for a field you leave blank.
          </p>
          <div className="grid grid-cols-1 gap-2 sm:grid-cols-2">
            <label className="flex flex-col gap-1">
              <span className="font-mono text-[10px] uppercase tracking-[0.1em] text-muted-foreground">Reported by</span>
              <input
                type="text"
                value={detail.reportedBy}
                onChange={(e) => setDetail((d) => ({ ...d, reportedBy: e.target.value }))}
                placeholder="defaults to your account"
                className="rounded-sm border border-border bg-background px-2 py-1 text-[12px] text-foreground"
              />
            </label>
            <label className="flex flex-col gap-1">
              <span className="font-mono text-[10px] uppercase tracking-[0.1em] text-muted-foreground">Observation source</span>
              <input
                type="text"
                value={detail.observationSource}
                onChange={(e) => setDetail((d) => ({ ...d, observationSource: e.target.value }))}
                placeholder="e.g. Coast Guard patrol report"
                className="rounded-sm border border-border bg-background px-2 py-1 text-[12px] text-foreground"
              />
            </label>
            <label className="flex flex-col gap-1">
              <span className="font-mono text-[10px] uppercase tracking-[0.1em] text-muted-foreground">Initial longitude</span>
              <input
                type="text"
                inputMode="decimal"
                value={detail.lon}
                onChange={(e) => setDetail((d) => ({ ...d, lon: e.target.value }))}
                placeholder="e.g. 72.60"
                className="rounded-sm border border-border bg-background px-2 py-1 font-mono text-[12px] text-foreground"
              />
            </label>
            <label className="flex flex-col gap-1">
              <span className="font-mono text-[10px] uppercase tracking-[0.1em] text-muted-foreground">Initial latitude</span>
              <input
                type="text"
                inputMode="decimal"
                value={detail.lat}
                onChange={(e) => setDetail((d) => ({ ...d, lat: e.target.value }))}
                placeholder="e.g. 18.90"
                className="rounded-sm border border-border bg-background px-2 py-1 font-mono text-[12px] text-foreground"
              />
            </label>
            <label className="flex flex-col gap-1">
              <span className="font-mono text-[10px] uppercase tracking-[0.1em] text-muted-foreground">Priority (your read)</span>
              <select
                value={detail.priority}
                onChange={(e) => setDetail((d) => ({ ...d, priority: e.target.value }))}
                className="rounded-sm border border-border bg-background px-2 py-1 text-[12px] text-foreground"
              >
                <option value="">unspecified</option>
                <option value="low">low</option>
                <option value="medium">medium</option>
                <option value="high">high</option>
                <option value="critical">critical</option>
              </select>
            </label>
            <label className="flex flex-col gap-1 sm:col-span-2">
              <span className="font-mono text-[10px] uppercase tracking-[0.1em] text-muted-foreground">Notes</span>
              <textarea
                value={detail.notes}
                onChange={(e) => setDetail((d) => ({ ...d, notes: e.target.value }))}
                rows={2}
                placeholder="Stored verbatim. Never parsed or acted on automatically."
                className="rounded-sm border border-border bg-background px-2 py-1 text-[12px] text-foreground"
              />
            </label>
          </div>
          <button
            type="button"
            disabled={busy}
            onClick={handleCreateWithDetails}
            className="mt-3 flex items-center gap-1.5 rounded-sm bg-primary px-3 py-1.5 text-[12px] font-semibold uppercase tracking-[0.08em] text-primary-foreground hover:bg-[var(--navy-muted)] disabled:opacity-40"
          >
            <FilePlus2 className="h-3.5 w-3.5" />
            {busy ? 'Creating…' : 'Create case with these details'}
          </button>
        </Card>
      )}

      {msg && (
        <p
          className={cn(
            'mb-3 rounded-sm border px-3 py-2 text-[12px]',
            msg.ok
              ? 'border-[color-mix(in_oklch,var(--ok)_40%,transparent)] bg-[color-mix(in_oklch,var(--ok)_8%,transparent)] text-[color-mix(in_oklch,var(--ok)_55%,black)]'
              : 'border-destructive/40 bg-destructive/5 text-destructive',
          )}
        >
          {msg.text}
        </p>
      )}
      {error && (
        <p className="mb-3 rounded-sm border border-destructive/40 bg-destructive/5 px-3 py-2 text-[12px] text-destructive">
          {error}
        </p>
      )}

      <Card title="Case register">
        {/* A real input. The previous "search" was a <div> with a <span>. */}
        <div className="mb-2 flex items-center gap-2 rounded-sm border border-border bg-background px-2.5 py-1.5">
          <Search className="h-3.5 w-3.5 shrink-0 text-muted-foreground" />
          <input
            type="text"
            value={query}
            onChange={(e) => setQuery(e.target.value)}
            placeholder="Filter by case id, status, validity or engine mode…"
            className="w-full bg-transparent text-[13px] text-foreground outline-none placeholder:text-muted-foreground"
          />
          {query && (
            <button
              type="button"
              onClick={() => setQuery('')}
              className="font-mono text-[10px] uppercase tracking-[0.08em] text-muted-foreground hover:text-foreground"
            >
              Clear
            </button>
          )}
        </div>

        {cases !== null && cases.length === 0 && !error && (
          <p className="text-[12px] leading-snug text-muted-foreground">
            No cases exist yet. Run a scenario from the cockpit, or create one with
            <strong> New Case</strong>. This is the honest empty state — no sample
            cases are invented to fill the table.
          </p>
        )}

        {filtered.length > 0 && (
          <div className="overflow-x-auto">
            <table className="w-full text-left">
              <thead>
                <tr className="border-b border-border">
                  {['Case', 'Status', 'Validity', 'Recommendation', 'Alerts', 'Missions', 'Mode', ''].map((h) => (
                    <th
                      key={h}
                      className="whitespace-nowrap pb-2 pr-4 font-mono text-[10px] font-semibold uppercase tracking-[0.12em] text-muted-foreground"
                    >
                      {h}
                    </th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {filtered.map((c) => (
                  <tr key={c.case_id} className="border-b border-border/50 last:border-b-0">
                    <td className="py-2.5 pr-4 font-mono text-[12px] font-medium text-foreground">
                      {c.case_id}
                    </td>
                    <td className="py-2.5 pr-4">
                      <StatusBadge tone={statusTone(c.status)}>{c.status}</StatusBadge>
                    </td>
                    <td className="py-2.5 pr-4">
                      {c.validity_state ? (
                        <StatusBadge tone={validityTone(c.validity_state)}>
                          {c.validity_state}
                        </StatusBadge>
                      ) : (
                        <span className="text-[12px] text-muted-foreground">—</span>
                      )}
                    </td>
                    <td className="py-2.5 pr-4 text-[13px] text-muted-foreground">
                      {c.recommendation ?? '—'}
                    </td>
                    <td className="py-2.5 pr-4 font-mono text-[12px] tabular-nums text-foreground">
                      {c.n_alerts}
                    </td>
                    <td className="py-2.5 pr-4 font-mono text-[12px] tabular-nums text-foreground">
                      {c.n_missions}
                    </td>
                    <td className="py-2.5 pr-4">
                      <EngineModeBadge mode={(c.engine_mode as never) ?? null} />
                    </td>
                    <td className="py-2.5">
                      {c.has_operator_view ? (
                        <Link
                          href={`/?case=${encodeURIComponent(c.case_id)}`}
                          className="flex items-center gap-1 font-mono text-[11px] uppercase tracking-[0.08em] text-muted-foreground hover:text-foreground"
                        >
                          Open <ChevronRight className="h-3 w-3" />
                        </Link>
                      ) : (
                        <span
                          title="This case has not been run, so there is no operator view to open."
                          className="font-mono text-[10px] uppercase tracking-[0.08em] text-muted-foreground/60"
                        >
                          not run
                        </span>
                      )}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}

        {cases !== null && cases.length > 0 && filtered.length === 0 && (
          <p className="text-[12px] text-muted-foreground">
            No case matches “{query}”.
          </p>
        )}
      </Card>
    </>
  )
}
