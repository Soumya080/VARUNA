'use client'

/**
 * VARUNA MISSION COCKPIT — the canonical demo surface.
 *
 * Driven end-to-end by ONE case:
 *   GoldenCaseWorkflow -> CaseResult -> build_product_case -> OperatorCase
 *
 * This file and everything under components/cockpit/ import NOTHING from
 * lib/mock-data. Every coordinate, status, score, alert and mission shown
 * here comes from the backend. Where the backend produced nothing, the
 * cockpit says so instead of substituting a placeholder.
 */
import dynamic from 'next/dynamic'
import Link from 'next/link'
import { useSearchParams } from 'next/navigation'
import { Suspense, useCallback, useEffect, useState } from 'react'
import { StatusBadge } from '@/components/primitives'
import { EngineModeBadge } from '@/components/evidence-mode-badge'
import { useAuth } from '@/lib/auth-context'
import { useRunStream } from '@/lib/use-run-stream'
import { deriveStageState } from '@/lib/stage-state'
import { ACTS } from '@/lib/stages'
import { OperatorCaseProvider } from '@/lib/operator-case-context'
import { UncertaintyPanel, ForecastPanel, DecisionTracePanel, SmritiPanel, PramanPanel } from '@/components/intelligence-panels'
import { VerificationLedger } from '@/components/verification-ledger'
import {
  acknowledgeAlert,
  approveMission,
  AuthActionError,
  escalateAlert,
  getOperationalSummary,
  getReplayOperatorCase,
  downloadReport,
  resolveAlert,
  type AlertLifecycleRecord,
} from '@/lib/api'
import { AlertCenter } from '@/components/cockpit/alert-center'
import { ChhayaPanelV2 } from '@/components/cockpit/chhaya-panel'
import { MarineContextPanel } from '@/components/cockpit/marine-context-panel'
import type { OperatorCase } from '@/lib/operator-case-types'
import { Card, EvidencePanels, Row, RunTimeline } from '@/components/cockpit/cockpit-panels'
import { cn } from '@/lib/utils'
import { Play, ShieldCheck, FileSearch, FileDown } from 'lucide-react'

// Leaflet touches `window` at import time — must not run during SSR.
const CaseMap = dynamic(() => import('@/components/cockpit/case-map'), {
  ssr: false,
  loading: () => (
    <div className="grid h-full min-h-[420px] place-items-center rounded-sm border border-border bg-card text-[12px] text-muted-foreground">
      Loading map…
    </div>
  ),
})

// Phase 5/6: Indian Ocean incidents lead (illustrative reconstructions of
// real events, see docs/product/INDIAN_OCEAN_FIXTURES.md); the original
// MC20 fixtures stay fully available but relabelled as the external
// validation case they are — real Sentinel-1 data, not a reconstruction,
// but Gulf-of-Mexico-anchored, not India. Never hidden, never merged.
const SCENARIOS = [
  { id: 'IND-CASE-01', label: 'IND-CASE-01', hint: '2017 BW Maple / Chennai collision (illustrative reconstruction)', group: 'india' },
  { id: 'IND-CASE-02', label: 'IND-CASE-02', hint: '2010 MSC Chitra / Mumbai collision (illustrative reconstruction)', group: 'india' },
  { id: 'IND-CASE-05', label: 'IND-CASE-05', hint: 'Mumbai High platform-source scenario, no vessel (illustrative)', group: 'india' },
  { id: 'CASE-VALID', label: 'MC20 · CASE-VALID', hint: 'External validation — real Sentinel-1, Gulf of Mexico', group: 'validation' },
  { id: 'CASE-OOD', label: 'MC20 · CASE-OOD', hint: 'External validation — fail-closed / out of distribution', group: 'validation' },
  { id: 'CASE-SIMULATED', label: 'MC20 · CASE-SIMULATED', hint: 'External validation — simulated evidence', group: 'validation' },
] as const

// Phase 7 (docs/product/HONESTY_LEDGER.md #22): the fake STORY array used
// to live here — 9 identical-class chips referencing no real state, not
// aligned to the backend's real 13 stages. Deleted outright; `ACTS` from
// `lib/stages.ts` (imported above) mirrors the real backend stage
// vocabulary and each chip is now a link to its real story page.

const REPLAY_FIXTURES = SCENARIOS.map((s) => s.id) as readonly string[]

/** Phase 11 fix (docs/product/HONESTY_LEDGER.md #30): `/?case=<id>` links
 * (sidebar "Other Cases", `/cases`) were constructed but never read by
 * this page — a dead link. Resolves a `REPLAY-{fixtureName}` case_id (the
 * only kind of case this cockpit's fetch/run/alert flow knows how to
 * drive) back to its fixture name. A legacy, non-replay case_id (created
 * via `POST /v1/cases`, not part of the real demo flow) has no fixture to
 * resolve to — returns null so the caller can say so honestly rather than
 * pretending to load it. */
function resolveFixtureFromCaseId(caseId: string | null): string | null {
  if (!caseId) return null
  const stripped = caseId.startsWith('REPLAY-') ? caseId.slice('REPLAY-'.length) : caseId
  return REPLAY_FIXTURES.includes(stripped) ? stripped : null
}

function MissionCockpitInner() {
  const { session, isAuthenticated, logout } = useAuth()
  const searchParams = useSearchParams()
  const requestedCaseId = searchParams.get('case')
  const [caseParamError, setCaseParamError] = useState<string | null>(null)
  const [fixture, setFixture] = useState<string>(() => resolveFixtureFromCaseId(requestedCaseId) ?? 'IND-CASE-01')

  useEffect(() => {
    if (!requestedCaseId) return
    const resolved = resolveFixtureFromCaseId(requestedCaseId)
    if (resolved) {
      setFixture(resolved)
      setCaseParamError(null)
    } else {
      setCaseParamError(
        `Case ${requestedCaseId} is not a replay case this cockpit can load — only the demo's replay fixtures (${REPLAY_FIXTURES.join(', ')}) are drivable here.`,
      )
    }
    // Only re-resolve when the URL's case param itself changes.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [requestedCaseId])
  const [oc, setOc] = useState<OperatorCase | null>(null)
  const [loadError, setLoadError] = useState<string | null>(null)
  const [alerts, setAlerts] = useState<AlertLifecycleRecord[]>([])
  const [channels, setChannels] = useState<Record<string, string>>({})
  // Live missions from MissionService. The composed OperatorCase is cached,
  // so oc.mission goes stale the moment a mission is approved — this is the
  // authoritative post-action state.
  const [liveMissions, setLiveMissions] = useState<Array<Record<string, unknown>>>([])
  const [busy, setBusy] = useState(false)
  const [downloading, setDownloading] = useState(false)

  async function handleDownloadReport() {
    if (!oc) return
    setDownloading(true)
    setActionMsg(null)
    try {
      await downloadReport(oc.case_id)
      setActionMsg({ text: 'Incident report downloaded.', ok: true })
    } catch (e) {
      // Surface the backend's own reason (404 = case not run in this process,
      // 503 = reportlab missing) rather than opening a blank tab.
      setActionMsg({
        text: e instanceof Error ? `Report unavailable — ${e.message}` : 'Report failed.',
        ok: false,
      })
    } finally {
      setDownloading(false)
    }
  }
  const [actionMsg, setActionMsg] = useState<{ text: string; ok: boolean } | null>(null)
  const { phase, events, summary, error: runError, run } = useRunStream()
  const stageStates = deriveStageState(oc, events, phase)

  const caseId = `REPLAY-${fixture}`

  const loadCase = useCallback(async (fx: string) => {
    setLoadError(null)
    try {
      const data = await getReplayOperatorCase(fx)
      setOc(data)
    } catch (e) {
      setOc(null)
      setLoadError(e instanceof Error ? e.message : 'Failed to load case')
    }
    try {
      const s = await getOperationalSummary(`REPLAY-${fx}`)
      setAlerts(s.alerts)
      setChannels(s.channels)
      setLiveMissions(s.missions ?? [])
    } catch {
      setAlerts([])
      setChannels({})
      setLiveMissions([])
    }
  }, [])

  useEffect(() => {
    loadCase(fixture)
  }, [fixture, loadCase])

  function handleRun() {
    setActionMsg(null)
    run(fixture, () => loadCase(fixture))
  }

  async function doAlertAction(
    alertId: string,
    action: 'acknowledge' | 'escalate' | 'resolve',
    label: string,
  ) {
    const fn =
      action === 'acknowledge' ? acknowledgeAlert : action === 'escalate' ? escalateAlert : resolveAlert
    setBusy(true)
    await doAction(() => fn(alertId), `${label} confirmed by backend.`)
    setBusy(false)
  }

  async function doAction(fn: () => Promise<unknown>, okText: string) {
    setActionMsg(null)
    if (!isAuthenticated) {
      setActionMsg({ text: 'NOT AUTHENTICATED — sign in (top right) first.', ok: false })
      return
    }
    try {
      await fn()
      setActionMsg({ text: okText, ok: true })
      await loadCase(fixture)
    } catch (e) {
      if (e instanceof AuthActionError) {
        if (e.status === 401) {
          logout()
          setActionMsg({ text: 'NOT AUTHENTICATED — session expired.', ok: false })
        } else {
          setActionMsg({
            text: `NOT AUTHORIZED — ${session?.role ?? 'your role'} lacks this permission.`,
            ok: false,
          })
        }
      } else {
        setActionMsg({ text: e instanceof Error ? e.message : 'Action failed.', ok: false })
      }
    }
  }

  const sp = oc?.starting_point
  const caseMission = oc?.mission.status === 'produced' ? oc.mission.value?.[0] : null
  // Prefer the LIVE MissionService record over the cached OperatorCase copy.
  const live = liveMissions.find(
    (m) => String(m.mission_id) === String(caseMission?.mission_id),
  )
  const mission = caseMission
    ? {
        ...caseMission,
        state: String(live?.state ?? caseMission.state),
        // Phase 9 fix: `caseMission.approved_by` never existed on the wire
        // (the real field is `human_approved_by`, see
        // lib/operator-case-types.ts) — the fallback below was always null.
        approved_by: (live?.human_approved_by as string | null) ?? caseMission.human_approved_by ?? null,
      }
    : null
  // A mission that is already ASSIGNED cannot be approved again — the FSM
  // rejects `assigned -> assigned` with a 400. Showing an enabled button
  // that always errors is what made authorization look broken.
  const alreadyAuthorized = Boolean(
    mission && (mission.approved_by || String(mission.state).toLowerCase() === 'assigned'),
  )
  const openAlert = alerts.find((a) => a.status !== 'resolved') ?? alerts[0] ?? null

  return (
    <>
      {/* ---------------- Header / story / system status ---------------- */}
      <div className="mb-3">
        <div className="flex flex-wrap items-end justify-between gap-2">
          <div>
            <h1 className="text-balance text-xl font-semibold leading-tight tracking-tight text-foreground">
              VARUNA Mission Cockpit
            </h1>
            <p className="mt-0.5 font-mono text-[12px] uppercase tracking-[0.1em] text-muted-foreground">
              Operational maritime oil-spill response · evidence to authorization
            </p>
          </div>
          <div className="flex items-center gap-2">
            {oc && <EngineModeBadge mode={oc.system_status.engine_mode ?? null} />}
            {oc && <StatusBadge tone="muted">{oc.case_id}</StatusBadge>}
          </div>
        </div>

        <ol className="mt-2 flex flex-wrap items-center gap-1">
          {ACTS.map((act, i) => {
            const actStages = stageStates.filter((s) => act.stages.includes(s.stage))
            const anyBad = actStages.some((s) => s.status === 'blocked' || s.status === 'error')
            const allDone = actStages.length > 0 && actStages.every((s) => s.status === 'produced')
            const anyDone = actStages.some((s) => s.status === 'produced')
            return (
              <li key={act.id} className="flex items-center gap-1">
                <Link
                  href={act.href}
                  className={cn(
                    'rounded-sm border px-1.5 py-0.5 font-mono text-[9px] font-semibold uppercase tracking-[0.1em] transition-colors hover:border-foreground/40',
                    anyBad
                      ? 'border-[color-mix(in_oklch,var(--destructive)_40%,transparent)] bg-[color-mix(in_oklch,var(--destructive)_8%,transparent)] text-[color-mix(in_oklch,var(--destructive)_55%,black)]'
                      : allDone
                        ? 'border-[color-mix(in_oklch,var(--ok)_35%,transparent)] bg-[color-mix(in_oklch,var(--ok)_8%,transparent)] text-[color-mix(in_oklch,var(--ok)_55%,black)]'
                        : anyDone
                          ? 'border-border bg-muted/40 text-foreground'
                          : 'border-border bg-card text-muted-foreground',
                  )}
                  title={actStages.map((s) => `${s.stage}: ${s.status}`).join(', ')}
                >
                  {act.label}
                </Link>
                {i < ACTS.length - 1 && <span className="text-muted-foreground/40">→</span>}
              </li>
            )
          })}
        </ol>
      </div>

      {/* ---------------- Scenario + RUN ---------------- */}
      <div className="mb-3 flex flex-wrap items-center gap-2 rounded-sm border border-border bg-card px-3 py-2">
        <span className="font-mono text-[10px] uppercase tracking-[0.12em] text-muted-foreground">
          Scenario
        </span>
        <span className="font-mono text-[9px] uppercase tracking-[0.1em] text-muted-foreground/70">Indian Ocean</span>
        {SCENARIOS.filter((s) => s.group === 'india').map((s) => (
          <button
            key={s.id}
            type="button"
            title={s.hint}
            onClick={() => setFixture(s.id)}
            className={cn(
              'rounded-sm border px-2.5 py-1 font-mono text-[11px] font-semibold uppercase tracking-[0.06em] transition-colors',
              fixture === s.id
                ? 'border-saffron bg-[color-mix(in_oklch,var(--saffron)_16%,transparent)] text-[color-mix(in_oklch,var(--saffron)_50%,black)]'
                : 'border-border bg-background text-muted-foreground hover:bg-muted',
            )}
          >
            {s.label}
          </button>
        ))}
        <span className="ml-2 font-mono text-[9px] uppercase tracking-[0.1em] text-muted-foreground/70">External validation</span>
        {SCENARIOS.filter((s) => s.group === 'validation').map((s) => (
          <button
            key={s.id}
            type="button"
            title={s.hint}
            onClick={() => setFixture(s.id)}
            className={cn(
              'rounded-sm border px-2.5 py-1 font-mono text-[11px] font-semibold uppercase tracking-[0.06em] transition-colors',
              fixture === s.id
                ? 'border-saffron bg-[color-mix(in_oklch,var(--saffron)_16%,transparent)] text-[color-mix(in_oklch,var(--saffron)_50%,black)]'
                : 'border-border bg-background text-muted-foreground hover:bg-muted',
            )}
          >
            {s.label}
          </button>
        ))}
        <button
          type="button"
          onClick={handleRun}
          disabled={phase === 'running'}
          className="ml-auto flex items-center gap-1.5 rounded-sm bg-primary px-3.5 py-1.5 text-[12px] font-semibold uppercase tracking-[0.08em] text-primary-foreground hover:bg-[var(--navy-muted)] disabled:opacity-50"
        >
          <Play className="h-3.5 w-3.5" />
          {phase === 'running' ? 'Running…' : 'Run VARUNA'}
        </button>
        <button
          type="button"
          disabled={!oc || downloading}
          onClick={handleDownloadReport}
          className="flex items-center gap-1.5 rounded-sm border border-saffron bg-[color-mix(in_oklch,var(--saffron)_14%,transparent)] px-3 py-1.5 text-[12px] font-semibold uppercase tracking-[0.08em] text-[color-mix(in_oklch,var(--saffron)_45%,black)] hover:bg-[color-mix(in_oklch,var(--saffron)_24%,transparent)] disabled:cursor-not-allowed disabled:opacity-40"
        >
          <FileDown className="h-3.5 w-3.5" />
          {downloading ? 'Generating…' : 'Download report'}
        </button>
        {summary && (
          <span className="font-mono text-[10px] tabular-nums text-muted-foreground">
            {summary.elapsed_ms.toFixed(0)}ms (workflow {summary.workflow_ms.toFixed(0)} · compose{' '}
            {summary.compose_ms.toFixed(0)})
          </span>
        )}
      </div>

      {caseParamError && (
        <p className="mb-3 rounded-sm border border-[color-mix(in_oklch,var(--warn)_45%,transparent)] bg-[color-mix(in_oklch,var(--warn)_8%,transparent)] px-3 py-2 text-[12px] text-[color-mix(in_oklch,var(--warn)_55%,black)]">
          {caseParamError}
        </p>
      )}
      {loadError && (
        <p className="mb-3 rounded-sm border border-destructive/40 bg-destructive/5 px-3 py-2 text-[12px] text-destructive">
          {loadError}
        </p>
      )}
      {runError && (
        <p className="mb-3 rounded-sm border border-destructive/40 bg-destructive/5 px-3 py-2 text-[12px] text-destructive">
          {runError}
        </p>
      )}

      {/* ---------------- 3-column cockpit ---------------- */}
      {/* Phase 8 fix #1 (docs/product/HONESTY_LEDGER.md #25): `items-start`
          — without it, the shortest column (the run timeline, ~5 rows)
          silently stretched to match the tallest, and every column's own
          content sat at a height determined by its neighbors rather than
          its own content. */}
      {/* OperatorCaseProvider with `value={oc}` (Phase 8): lets the new
          intelligence-panels.tsx panels below resolve via
          useOperatorCaseData() without a second fetch of the same case —
          the cockpit's own `oc` state already has it. */}
      <OperatorCaseProvider fixtureName={fixture} value={oc}>
      <div className="grid items-start gap-3 lg:grid-cols-[260px_minmax(0,1fr)_320px]">
        {/* LEFT — run timeline */}
        <div className="space-y-2">
          <Card title="Execution timeline">
            <RunTimeline stages={stageStates} />
            {phase === 'idle' && (
              <p className="mt-2 text-[11px] leading-snug text-muted-foreground">
                Press <strong>Run VARUNA</strong> to execute the canonical chain and stream
                real stage events from the backend.
              </p>
            )}
          </Card>
        </div>

        {/* CENTER — real map */}
        <div className="space-y-2">
          <Card
            title="Operational map"
            right={
              sp ? (
                <StatusBadge tone={sp.status === 'STARTING_POINT_AVAILABLE' ? 'ok' : 'warn'}>
                  {sp.status.replace('STARTING_POINT_', '')}
                </StatusBadge>
              ) : undefined
            }
          >
            {/* Phase 8 fix #2: the map used to be pinned to a literal
                460px regardless of viewport — dead space on a tall
                screen, cramped on a short one. Fills the available height
                instead, clamped to a sane range. */}
            <div className="h-[clamp(460px,60vh,760px)]">{oc ? <CaseMap operatorCase={oc} /> : null}</div>
            <div className="mt-2 flex flex-wrap items-center gap-x-4 gap-y-1 text-[11px] text-muted-foreground">
              <span>
                <span className="mr-1 inline-block h-2 w-2 rounded-full bg-[#dc2626]" />
                Starting point
              </span>
              <span>
                <span className="mr-1 inline-block h-2 w-2 bg-[#e8871a]" />
                NETRA detection
              </span>
              <span>
                <span className="mr-1 inline-block h-2 w-2 bg-[#3b82f6]" />
                PRATIVARTAN Φ
              </span>
              <span>
                <span className="mr-1 inline-block h-2 w-2 rounded-full bg-[#8b5cf6]" />
                Backdrift path
              </span>
              <span>
                <span className="mr-1 inline-block h-2 w-2 rounded-full border border-[#a78bfa] bg-transparent" />
                Source region
              </span>
              <span>
                <span className="mr-1 inline-block h-2 w-2 rounded-full border border-dashed border-[#ef4444] bg-transparent" />
                Latent L0
              </span>
              <span>
                <span className="mr-1 inline-block h-2 w-2 rounded-full bg-[#f59e0b]" />
                Origin scenarios
              </span>
              <span>
                <span className="mr-1 inline-block h-2 w-2 rounded-full bg-[#22c55e]" />
                PRAVAAH landfall
              </span>
              <span className="ml-auto font-mono">
                LAND MASK{' '}
                <strong className="text-[color-mix(in_oklch,var(--warn)_55%,black)]">
                  {(sp?.land_classification ?? 'unknown_no_landmask') === 'unknown_no_landmask'
                    ? 'UNKNOWN / NOT AVAILABLE'
                    : sp!.land_classification.toUpperCase()}
                </strong>
              </span>
            </div>
          </Card>

          <Card title="Starting point">
            {sp?.status === 'STARTING_POINT_AVAILABLE' && sp.point ? (
              <div className="grid grid-cols-2 gap-x-4">
                <Row
                  label="Latitude"
                  value={`${Math.abs(sp.point.lat).toFixed(3)}° ${sp.point.lat >= 0 ? 'N' : 'S'}`}
                />
                <Row
                  label="Longitude"
                  value={`${Math.abs(sp.point.lon).toFixed(3)}° ${sp.point.lon >= 0 ? 'E' : 'W'}`}
                />
                <Row label="Source" value={sp.source.replace(/_/g, ' ')} />
                <Row label="Contract" value={sp.status.replace('STARTING_POINT_', '')} />
              </div>
            ) : (
              <p className="text-[12px] text-muted-foreground">
                <strong>{sp?.status ?? 'STARTING_POINT_UNAVAILABLE'}</strong> —{' '}
                {sp?.reason ?? 'no starting point resolved for this case.'}
              </p>
            )}
          </Card>

          {/* Phase 8 fix #3 (docs/product/HONESTY_LEDGER.md #25): CHHAYA-V
              (tile mini-map + candidate evidence table — a wide-format
              artifact) used to be crammed into the 320px right rail, the
              narrowest column, alongside everything else. Moved here, into
              the ~900px center column, where it actually has room. */}
          <ChhayaPanelV2 />

          {/* Phase 8 fix #4: the six real, complete, previously-unmounted
              panels from components/intelligence-panels.tsx. `ChhayaPanel`
              (CHHAYA-H) is deliberately NOT duplicated here —
              `EvidencePanels` in the right rail already surfaces a compact
              CHHAYA-H summary card; mounting the fuller version right next
              to it would be redundant, not additive. */}
          <UncertaintyPanel />
          <ForecastPanel />
          <DecisionTracePanel />
        </div>

        {/* RIGHT — evidence + intelligence */}
        <div className="space-y-2">
          {oc ? <EvidencePanels oc={oc} /> : null}
          <SmritiPanel />
          <PramanPanel />
          <MarineContextPanel />
        </div>
      </div>
      </OperatorCaseProvider>

      {/* ---------------- Alert Center (Workstream A) ---------------- */}
      <div className="mt-3">
        <AlertCenter
          alerts={alerts}
          channels={channels}
          onAction={doAlertAction}
          busy={busy}
        />
      </div>

      {/* ---------------- BOTTOM — action / mission / PRAMAN / report ---------------- */}
      <div className="mt-3 grid gap-3 lg:grid-cols-4">
        <Card title="Recommended action">
          {oc ? (
            <>
              <StatusBadge
                tone={
                  oc.recommendation === 'valid'
                    ? 'ok'
                    : oc.recommendation === 'restricted'
                      ? 'destructive'
                      : 'muted'
                }
                dot
              >
                {oc.recommendation}
              </StatusBadge>
              <p className="mt-1.5 text-[12px] leading-snug text-muted-foreground">
                {oc.recommendation === 'valid'
                  ? 'Validity gate allows an operational action for this case.'
                  : (oc.validity.reason ??
                    'Evidence does not support an operational recommendation.')}
              </p>
              <button
                type="button"
                onClick={() =>
                  document.getElementById('praman-card')?.scrollIntoView({ behavior: 'smooth' })
                }
                className="mt-2 flex w-full items-center justify-center gap-1.5 rounded-sm border border-border bg-background px-2 py-1.5 text-[11px] font-semibold uppercase tracking-[0.08em] hover:bg-muted"
              >
                <FileSearch className="h-3 w-3" /> Review evidence
              </button>
            </>
          ) : (
            <p className="text-[12px] text-muted-foreground">No case loaded.</p>
          )}
        </Card>

        <Card title="Mission">
          {mission ? (
            <>
              <Row label="Mission" value={mission.mission_id} />
              <Row
                label="State"
                value={
                  <StatusBadge tone={mission.state === 'assigned' ? 'ok' : 'muted'}>
                    {mission.state}
                  </StatusBadge>
                }
              />
              <Row
                label="Approved by"
                value={mission.approved_by ?? 'not yet approved'}
              />
              {alreadyAuthorized ? (
                <div className="mt-2 rounded-sm border border-[color-mix(in_oklch,var(--ok)_40%,transparent)] bg-[color-mix(in_oklch,var(--ok)_8%,transparent)] px-2 py-1.5 text-center text-[11px] font-semibold uppercase tracking-[0.08em] text-[color-mix(in_oklch,var(--ok)_55%,black)]">
                  <ShieldCheck className="mr-1 inline h-3 w-3" />
                  Authorized by {mission.approved_by}
                </div>
              ) : (
                <button
                  type="button"
                  disabled={!isAuthenticated || busy}
                  title={
                    isAuthenticated
                      ? 'Calls POST /v1/missions/{id}/approve with your JWT.'
                      : 'Sign in first — mission authorization is backend-enforced.'
                  }
                  onClick={() =>
                    doAction(
                      () => approveMission(mission.mission_id, session?.username ?? ''),
                      'Mission authorized — confirmed by backend.',
                    )
                  }
                  className="mt-2 flex w-full items-center justify-center gap-1.5 rounded-sm bg-primary px-2 py-1.5 text-[11px] font-semibold uppercase tracking-[0.08em] text-primary-foreground hover:bg-[var(--navy-muted)] disabled:cursor-not-allowed disabled:opacity-40"
                >
                  <ShieldCheck className="h-3 w-3" />
                  {isAuthenticated ? 'Authorize mission' : 'Sign in to authorize'}
                </button>
              )}
            </>
          ) : (
            <p className="text-[12px] text-muted-foreground">
              {oc?.mission.reason ?? 'No mission proposed for this case.'}
            </p>
          )}
        </Card>

        <Card title="PRAMAN — provenance" id="praman-card">
          {oc ? (
            <>
              <Row label="Case" value={oc.case_id} />
              <Row label="Run" value={summary?.run_id ?? '—'} />
              <Row label="Artifacts" value={oc.provenance.artifact_ids?.length ?? 0} />
              <Row label="Actor" value={session?.username ?? 'not signed in'} />
              <Row
                label="Generated"
                value={new Date(oc.generated_at).toISOString().slice(11, 19) + 'Z'}
              />
              {(oc.provenance.model_versions
                ? Object.entries(oc.provenance.model_versions)
                : []
              ).map(([k, v]) => (
                <Row key={k} label={k} value={String(v)} />
              ))}
              <button
                type="button"
                disabled={downloading}
                onClick={handleDownloadReport}
                className="mt-2 flex w-full items-center justify-center gap-1.5 rounded-sm border border-border bg-background px-2 py-1.5 text-[11px] font-semibold uppercase tracking-[0.08em] hover:bg-muted disabled:opacity-40"
              >
                <FileDown className="h-3 w-3" />
                {downloading ? 'Generating…' : 'Download incident report (PDF)'}
              </button>
            </>
          ) : (
            <p className="text-[12px] text-muted-foreground">No case loaded.</p>
          )}
        </Card>

        {/* Phase 8 fix #5 (docs/product/HONESTY_LEDGER.md #25): this row's
            4th cell was permanently empty on any screen wide enough for
            4 columns — this row is already action/mission/PRAMAN, and
            verification (Phase 6B) belongs right beside authorization. */}
        <Card title="Verification">
          {oc ? <VerificationLedger oc={oc} /> : <p className="text-[12px] text-muted-foreground">No case loaded.</p>}
        </Card>
      </div>

      {actionMsg && (
        <p
          className={cn(
            'mt-2 rounded-sm border px-3 py-2 text-[12px]',
            actionMsg.ok
              ? 'border-[color-mix(in_oklch,var(--ok)_40%,transparent)] bg-[color-mix(in_oklch,var(--ok)_8%,transparent)] text-[color-mix(in_oklch,var(--ok)_55%,black)]'
              : 'border-destructive/40 bg-destructive/5 text-destructive',
          )}
        >
          {actionMsg.text}
        </p>
      )}
    </>
  )
}

export default function MissionCockpit() {
  return (
    <Suspense fallback={<p className="text-[12px] text-muted-foreground">Loading…</p>}>
      <MissionCockpitInner />
    </Suspense>
  )
}
