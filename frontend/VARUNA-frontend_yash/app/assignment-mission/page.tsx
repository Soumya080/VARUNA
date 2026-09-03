'use client'

/**
 * Assignment & Mission — real, backed by the Phase 4 mission FSM.
 *
 * Replaces a fully mock page: a hardcoded ASSIGNMENTS/FEASIBILITY table, a
 * fabricated green "Authorization Workflow" checklist with invented actors
 * and timestamps, and a "Request Authorization" button with no handler.
 *
 * Everything here is the backend's own state. Actions offered are exactly
 * the FSM's legal next states (GET /v1/missions/{id}/transitions), so the UI
 * never presents a move the system would reject.
 */
import { useCallback, useEffect, useState } from 'react'
import { Card, Row } from '@/components/cockpit/cockpit-panels'
import { StatusBadge } from '@/components/primitives'
import { useAuth } from '@/lib/auth-context'
import {
  approveMission, AuthActionError, cancelMission, createMission, listAssets,
  listCases, listCaseMissions, listPersonnel, missionHistory, missionTransitions,
  transitionMission, type AssetRow, type CaseRow, type MissionRow, type PersonnelRow,
} from '@/lib/api'
import { cn } from '@/lib/utils'
import { Ban, Plane, PlusCircle, RefreshCw, ShieldCheck, Ship } from 'lucide-react'

function stateTone(s: string) {
  if (['assigned', 'acknowledged', 'en_route', 'on_station', 'searching'].includes(s))
    return 'ok' as const
  if (['contact', 'confirmed'].includes(s)) return 'saffron' as const
  if (['complete', 'closed'].includes(s)) return 'muted' as const
  if (['not_found', 'reassigned'].includes(s)) return 'destructive' as const
  return 'warn' as const
}

interface Enriched extends MissionRow {
  legal_next?: string[]
  terminal?: boolean
  history?: Array<{ state: string; at: string; reason: string | null }>
}

export default function AssignmentMissionPage() {
  const { session, isAuthenticated, logout } = useAuth()
  const [missions, setMissions] = useState<Enriched[] | null>(null)
  const [msg, setMsg] = useState<{ text: string; ok: boolean } | null>(null)
  const [busy, setBusy] = useState(false)
  const [openId, setOpenId] = useState<string | null>(null)

  // New-assignment form state (Phase 4).
  const [cases, setCases] = useState<CaseRow[]>([])
  const [availableAssets, setAvailableAssets] = useState<AssetRow[]>([])
  const [onDutyOfficers, setOnDutyOfficers] = useState<PersonnelRow[]>([])
  const [newCaseId, setNewCaseId] = useState('')
  const [newAssetId, setNewAssetId] = useState('')
  const [showNewAssignment, setShowNewAssignment] = useState(false)

  const load = useCallback(async () => {
    try {
      const cases = (await listCases()).items
      const all: Enriched[] = []
      for (const c of cases) {
        const { items } = await listCaseMissions(c.case_id)
        for (const m of items) {
          const enriched: Enriched = { ...m }
          try {
            const t = await missionTransitions(m.mission_id)
            enriched.legal_next = t.legal_next
            enriched.terminal = t.terminal
          } catch {
            /* leave undefined; the UI shows no actions rather than guessing */
          }
          try {
            enriched.history = (await missionHistory(m.mission_id)).history
          } catch {
            /* history is optional detail */
          }
          all.push(enriched)
        }
      }
      setMissions(all)
      setCases(cases)
    } catch {
      setMissions([])
    }
    try {
      const [assetsRes, personnelRes] = await Promise.all([
        listAssets({ status: 'available' }),
        listPersonnel({ role: 'duty_officer', onDutyOnly: true }),
      ])
      setAvailableAssets(assetsRes.items)
      setOnDutyOfficers(personnelRes.items)
    } catch {
      setAvailableAssets([])
      setOnDutyOfficers([])
    }
  }, [])

  useEffect(() => {
    load()
  }, [load])

  async function handleCreateAssignment() {
    setMsg(null)
    if (!isAuthenticated) {
      setMsg({ text: 'NOT AUTHENTICATED — sign in (top right) first.', ok: false })
      return
    }
    if (!newCaseId || !newAssetId) {
      setMsg({ text: 'Pick both a case and an available asset.', ok: false })
      return
    }
    setBusy(true)
    try {
      const created = await createMission(newCaseId, newAssetId)
      setMsg({
        text: `Mission ${created.mission_id} proposed against ${newAssetId} — confirmed by backend. Authorize it below to dispatch.`,
        ok: true,
      })
      setShowNewAssignment(false)
      setNewCaseId('')
      setNewAssetId('')
      await load()
    } catch (e) {
      if (e instanceof AuthActionError) {
        if (e.status === 401) {
          logout()
          setMsg({ text: 'NOT AUTHENTICATED — session expired.', ok: false })
        } else {
          setMsg({
            text: `NOT AUTHORIZED — ${session?.role ?? 'your role'} lacks CREATE_MISSION.`,
            ok: false,
          })
        }
      } else {
        setMsg({ text: e instanceof Error ? e.message : 'Assignment failed.', ok: false })
      }
    } finally {
      setBusy(false)
    }
  }

  async function act(fn: () => Promise<unknown>, okText: string) {
    setMsg(null)
    if (!isAuthenticated) {
      setMsg({ text: 'NOT AUTHENTICATED — sign in (top right) first.', ok: false })
      return
    }
    setBusy(true)
    try {
      await fn()
      setMsg({ text: okText, ok: true })
      await load()
    } catch (e) {
      if (e instanceof AuthActionError) {
        if (e.status === 401) {
          logout()
          setMsg({ text: 'NOT AUTHENTICATED — session expired.', ok: false })
        } else {
          setMsg({
            text: `NOT AUTHORIZED — ${session?.role ?? 'your role'} lacks mission-approval permission.`,
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

  return (
    <>
      <div className="mb-3 flex flex-wrap items-end justify-between gap-2">
        <div>
          <h1 className="text-balance text-xl font-semibold leading-tight tracking-tight text-foreground">
            Assignment &amp; Mission
          </h1>
          <p className="mt-0.5 font-mono text-[12px] uppercase tracking-[0.1em] text-muted-foreground">
            {missions === null
              ? 'Loading…'
              : `${missions.length} mission${missions.length === 1 ? '' : 's'} · live FSM state`}
          </p>
        </div>
        <div className="flex flex-wrap items-center gap-2">
          <button
            type="button"
            onClick={() => setShowNewAssignment((v) => !v)}
            className="flex items-center gap-1.5 rounded-sm bg-primary px-3 py-1.5 text-[12px] font-semibold uppercase tracking-[0.08em] text-primary-foreground hover:bg-[var(--navy-muted)]"
          >
            <PlusCircle className="h-3.5 w-3.5" /> New assignment
          </button>
          <button
            type="button"
            onClick={load}
            className="flex items-center gap-1.5 rounded-sm border border-border bg-card px-3 py-1.5 text-[12px] font-semibold uppercase tracking-[0.08em] text-muted-foreground hover:bg-muted"
          >
            <RefreshCw className="h-3.5 w-3.5" /> Refresh
          </button>
        </div>
      </div>

      {showNewAssignment && (
        <Card title="New assignment">
          <p className="mb-2 text-[12px] text-muted-foreground">
            Pick a case and a real, currently-available asset. This proposes
            the mission only — authorizing dispatch is a separate step below,
            per the two-step approval gate.
          </p>
          <div className="grid grid-cols-1 gap-2 sm:grid-cols-3">
            <label className="flex flex-col gap-1">
              <span className="font-mono text-[10px] uppercase tracking-[0.1em] text-muted-foreground">Case</span>
              <select
                value={newCaseId}
                onChange={(e) => setNewCaseId(e.target.value)}
                className="rounded-sm border border-border bg-background px-2 py-1 text-[12px] text-foreground"
              >
                <option value="">select a case…</option>
                {cases.map((c) => <option key={c.case_id} value={c.case_id}>{c.case_id}</option>)}
              </select>
            </label>
            <label className="flex flex-col gap-1">
              <span className="font-mono text-[10px] uppercase tracking-[0.1em] text-muted-foreground">Available asset</span>
              <select
                value={newAssetId}
                onChange={(e) => setNewAssetId(e.target.value)}
                className="rounded-sm border border-border bg-background px-2 py-1 text-[12px] text-foreground"
              >
                <option value="">select an asset…</option>
                {availableAssets.map((a) => (
                  <option key={a.asset_id} value={a.asset_id}>{a.name} ({a.kind}, {a.home_base})</option>
                ))}
              </select>
              {availableAssets.length === 0 && (
                <span className="text-[11px] text-muted-foreground">No assets currently available — see Assets.</span>
              )}
            </label>
            <label className="flex flex-col gap-1">
              <span className="font-mono text-[10px] uppercase tracking-[0.1em] text-muted-foreground">On-duty officers (context)</span>
              <div className="rounded-sm border border-border bg-background px-2 py-1 text-[12px] text-muted-foreground">
                {onDutyOfficers.length > 0
                  ? onDutyOfficers.map((p) => p.name).join(', ')
                  : 'none on duty'}
              </div>
            </label>
          </div>
          <button
            type="button"
            disabled={busy || !newCaseId || !newAssetId}
            onClick={handleCreateAssignment}
            className="mt-3 flex items-center gap-1.5 rounded-sm bg-primary px-3 py-1.5 text-[12px] font-semibold uppercase tracking-[0.08em] text-primary-foreground hover:bg-[var(--navy-muted)] disabled:opacity-40"
          >
            <PlusCircle className="h-3.5 w-3.5" />
            {busy ? 'Creating…' : 'Propose mission'}
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

      {missions !== null && missions.length === 0 && (
        <Card title="Missions">
          <p className="text-[12px] leading-snug text-muted-foreground">
            No missions exist. A mission is proposed by the pipeline when a case
            produces an ABHIYAN tasking — run <strong>CASE-VALID</strong> from the
            cockpit. No sample missions are invented to fill this page.
          </p>
        </Card>
      )}

      <div className="space-y-3">
        {(missions ?? []).map((m) => {
          const approved = Boolean(m.human_approved_by)
          const open = openId === m.mission_id
          const t = m.tasking
          const isAir = (t?.asset_type ?? '').toLowerCase().includes('dornier')
          return (
            <Card
              key={m.mission_id}
              title={m.mission_id}
              right={
                <div className="flex flex-wrap items-center gap-1.5">
                  <StatusBadge tone={stateTone(m.state)} dot>
                    {m.state.replace(/_/g, ' ')}
                  </StatusBadge>
                  {approved && <StatusBadge tone="ok">authorized</StatusBadge>}
                  {m.terminal && <StatusBadge tone="muted">terminal</StatusBadge>}
                </div>
              }
            >
              <div className="grid gap-x-6 gap-y-1 sm:grid-cols-2">
                <Row label="Case" value={m.case_id} />
                <Row label="Asset" value={m.asset_id} />
                <Row
                  label="Approved by"
                  value={m.human_approved_by ?? 'not yet authorized'}
                />
                <Row label="Assigned at" value={m.assigned_at ?? '—'} />
              </div>

              {/* Real tasking — persisted since ADR-0015; previously discarded. */}
              <div className="mt-2 border-t border-border pt-2">
                <div className="mb-1 flex items-center gap-1.5">
                  {isAir ? (
                    <Plane className="h-3.5 w-3.5 text-saffron" />
                  ) : (
                    <Ship className="h-3.5 w-3.5 text-teal" />
                  )}
                  <span className="font-mono text-[10px] uppercase tracking-[0.1em] text-muted-foreground">
                    Tasking
                  </span>
                </div>
                {t ? (
                  <div className="grid gap-x-6 gap-y-1 sm:grid-cols-2">
                    <Row label="Asset type" value={t.asset_type ?? '—'} />
                    <Row label="Base" value={t.base_name ?? '—'} />
                    <Row label="Pattern" value={t.pattern ?? '—'} />
                    <Row label="Flight hours" value={t.flight_hours ?? '—'} />
                    <Row
                      label="Search area"
                      value={t.search_box?.area_km2 != null ? `${t.search_box.area_km2} km²` : '—'}
                    />
                    <Row
                      label="P(detection)"
                      value={t.probability_of_detection ?? '—'}
                    />
                    {t.search_box?.center && (
                      <Row
                        label="Search centre"
                        value={`${t.search_box.center.lat.toFixed(3)}, ${t.search_box.center.lon.toFixed(3)}`}
                      />
                    )}
                    {t.rationale && (
                      <div className="sm:col-span-2">
                        <p className="mt-1 text-[12px] leading-snug text-muted-foreground">
                          {t.rationale}
                        </p>
                      </div>
                    )}
                  </div>
                ) : (
                  <p className="text-[12px] text-muted-foreground">
                    No tasking recorded for this mission.
                  </p>
                )}
              </div>

              {/* Actions = exactly the FSM's legal next states. */}
              <div className="mt-3 flex flex-wrap items-center gap-1.5 border-t border-border pt-2">
                {!approved && (
                  <button
                    type="button"
                    disabled={busy || !isAuthenticated}
                    onClick={() =>
                      act(() => approveMission(m.mission_id, session?.username ?? ''),
                          'Mission authorized — confirmed by backend.')}
                    className="flex items-center gap-1.5 rounded-sm bg-primary px-2.5 py-1.5 text-[11px] font-semibold uppercase tracking-[0.08em] text-primary-foreground hover:bg-[var(--navy-muted)] disabled:opacity-40"
                  >
                    <ShieldCheck className="h-3 w-3" />
                    {isAuthenticated ? 'Authorize mission' : 'Sign in to authorize'}
                  </button>
                )}

                {(m.legal_next ?? [])
                  .filter((s) => s !== 'reserved' || approved)
                  .map((s) => (
                    <button
                      key={s}
                      type="button"
                      disabled={busy}
                      onClick={() =>
                        act(() => transitionMission(m.mission_id, s,
                              `advanced to ${s} by ${session?.username ?? 'operator'}`),
                            `Mission → ${s.replace(/_/g, ' ')} — confirmed by backend.`)}
                      className="rounded-sm border border-border bg-card px-2.5 py-1.5 text-[11px] font-medium hover:bg-muted disabled:opacity-40"
                    >
                      {s.replace(/_/g, ' ')}
                    </button>
                  ))}

                {approved && !m.terminal && (
                  <button
                    type="button"
                    disabled={busy}
                    onClick={() =>
                      act(() => cancelMission(m.mission_id, 'cancelled by operator'),
                          'Mission cancelled — confirmed by backend.')}
                    className="flex items-center gap-1.5 rounded-sm border border-destructive/40 bg-destructive/5 px-2.5 py-1.5 text-[11px] font-medium text-destructive hover:bg-destructive/10 disabled:opacity-40"
                  >
                    <Ban className="h-3 w-3" /> Cancel
                  </button>
                )}

                {m.terminal && (
                  <span className="text-[11px] text-muted-foreground">
                    Terminal state — no further transitions are legal.
                  </span>
                )}

                <button
                  type="button"
                  onClick={() => setOpenId(open ? null : m.mission_id)}
                  className="ml-auto font-mono text-[10px] uppercase tracking-[0.08em] text-muted-foreground hover:text-foreground"
                >
                  {open ? 'Hide history' : 'History'}
                </button>
              </div>

              {open && (
                <ol className="mt-2 space-y-0.5 border-t border-border pt-2">
                  {(m.history ?? []).length === 0 && (
                    <li className="text-[11px] text-muted-foreground">
                      No recorded transitions yet.
                    </li>
                  )}
                  {(m.history ?? []).map((h, i) => (
                    <li key={i} className="font-mono text-[10px] text-muted-foreground">
                      <span className="text-foreground">{h.state}</span> · {h.at}
                      {h.reason ? ` · ${h.reason}` : ''}
                    </li>
                  ))}
                </ol>
              )}
            </Card>
          )
        })}
      </div>
    </>
  )
}
