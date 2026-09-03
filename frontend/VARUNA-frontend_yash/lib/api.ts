/**
 * VARUNA backend API client (STEP 4, frontend integration track).
 *
 * The ONLY place `fetch()` is called against the VARUNA backend. Every
 * value this returns comes from the real API response — this module never
 * fabricates, defaults, or recomputes a scientific value. When the backend
 * is unreachable or returns an error, callers get a typed `ApiError`, never
 * a silently-substituted mock.
 */
import type { OperatorCase } from './operator-case-types'

export const API_BASE_URL =
  process.env.NEXT_PUBLIC_VARUNA_API_URL ?? 'http://localhost:8000'

export class ApiError extends Error {
  constructor(
    message: string,
    public status?: number,
  ) {
    super(message)
    this.name = 'ApiError'
  }
}

async function getJson<T>(path: string): Promise<T> {
  let response: Response
  try {
    response = await fetch(`${API_BASE_URL}${path}`, {
      headers: { Accept: 'application/json' },
      cache: 'no-store',
    })
  } catch (err) {
    throw new ApiError(
      `Could not reach the VARUNA backend at ${API_BASE_URL}${path}. ` +
        `Is the API server running? (${err instanceof Error ? err.message : String(err)})`,
    )
  }
  if (!response.ok) {
    let detail = response.statusText
    try {
      const body = await response.json()
      detail = body?.detail ?? body?.message ?? detail
    } catch {
      // response body wasn't JSON; keep statusText
    }
    throw new ApiError(detail, response.status)
  }
  return response.json() as Promise<T>
}

/** GET /v1/replay/fixtures */
export function listReplayFixtures(): Promise<{ fixtures: string[] }> {
  return getJson('/v1/replay/fixtures')
}

/**
 * GET /v1/replay/{fixtureName} — a replay case run through
 * GoldenCaseWorkflow and composed via build_product_case() (ADR-0013/0014).
 * This is the ONLY source of a fully-populated (intelligence.status ===
 * "produced") OperatorCase today — see docs/architecture/ADR-0014.
 */
export function getReplayOperatorCase(fixtureName: string): Promise<OperatorCase> {
  return getJson(`/v1/replay/${encodeURIComponent(fixtureName)}`)
}

/**
 * GET /v1/cases/{caseId}/operator-view — the live case route. Still backed
 * by the legacy CaseWorkflow (STEP 1), so `intelligence.status` will be
 * "not_yet_produced" for every case today — that is the honest, correct
 * backend behavior, not a frontend bug. See docs/architecture/ADR-0013.
 */
export function getCaseOperatorView(caseId: string): Promise<OperatorCase> {
  return getJson(`/v1/cases/${encodeURIComponent(caseId)}/operator-view`)
}

// ─────────────────────── STEP 6: alert lifecycle ───────────────────────
//
// No login/token-issuing endpoint exists in this backend yet (see
// apps/api/security.py's own docstring) and `demo_mode` is `false` in this
// deployment's .env, so every lifecycle action below genuinely returns 401
// until a real authenticated session exists. That is not a frontend bug to
// paper over — see `AuthActionError` below, which callers use to render an
// honest "NOT AUTHORIZED" state (Phase 9's explicit requirement) instead of
// silently failing or faking a mutation.

export interface NotificationDeliveryView {
  delivery_id: string
  channel: string
  recipient_role: string
  status: 'PENDING' | 'SENT' | 'DELIVERED' | 'FAILED' | 'NOT_CONFIGURED'
  mode: 'REAL' | 'SIMULATED' | 'NOT_CONFIGURED'
  provider: string | null
  error: string | null
  detail: string | null
  timestamp: string
}

export interface RoutingView {
  dimension: string
  severity: string
  recipients: Array<{ role: string; rbac_role: string | null; reason: string }>
  matched_rule: string
  reason: string
}

export interface AlertTransition {
  from: string
  to: string
  actor: string
  reason: string
  at: string
  detail: Record<string, unknown>
}

export interface OperationalSummary {
  case_id: string
  alerts: AlertLifecycleRecord[]
  missions: Array<Record<string, unknown>>
  channels: Record<string, string>
}

export interface AlertLifecycleRecord {
  alert_id: string
  case_id: string
  event_type: string
  severity: 'info' | 'warning' | 'blocked' | 'critical'
  reason: string
  is_simulated: boolean
  evidence_mode: string | null
  status:
    | 'created' | 'routed' | 'delivery_pending' | 'delivered'
    | 'acknowledged' | 'escalated' | 'resolved'
  material_dimension: string | null
  severity_basis: string | null
  previous_value: unknown
  current_value: unknown
  evidence_refs: string[]
  routing: RoutingView | null
  engine_mode: string | null
  transitions: AlertTransition[]
  deliveries: NotificationDeliveryView[]
  created_at: string
  acknowledged_by: string | null
  acknowledged_at: string | null
  escalated_by: string | null
  escalated_at: string | null
  resolved_by: string | null
  resolved_at: string | null
}

export class AuthActionError extends ApiError {
  constructor(message: string, status: number) {
    super(message, status)
    this.name = 'AuthActionError'
  }
}

// STEP 7: set by `lib/auth-context.tsx` on login/logout/session restore.
// A plain module variable, not React state — this file is not a component
// and every call site (including ones outside the auth provider's tree,
// like server-rendered code paths) needs a single source of truth for
// "what token, if any, should THIS request carry."
let _authToken: string | null = null

export function setAuthToken(token: string | null): void {
  _authToken = token
}

function authHeaders(): Record<string, string> {
  return _authToken ? { Authorization: `Bearer ${_authToken}` } : {}
}

export interface LoginResult {
  access_token: string
  token_type: string
  role: string
  expires_in_seconds: number
}

/** POST /v1/auth/login — never sends a role; the backend derives it
 * server-side from its own demo user registry (varuna_infra.demo_users). */
export async function login(username: string, password: string): Promise<LoginResult> {
  let response: Response
  try {
    response = await fetch(`${API_BASE_URL}/v1/auth/login`, {
      method: 'POST',
      headers: { Accept: 'application/json', 'Content-Type': 'application/json' },
      body: JSON.stringify({ username, password }),
    })
  } catch (err) {
    throw new ApiError(
      `Could not reach the VARUNA backend at ${API_BASE_URL}/v1/auth/login. ` +
        `(${err instanceof Error ? err.message : String(err)})`,
    )
  }
  if (!response.ok) {
    let detail = response.statusText
    try {
      const body = await response.json()
      detail = body?.detail ?? body?.message ?? detail
    } catch {
      // not JSON
    }
    throw new AuthActionError(detail, response.status)
  }
  return response.json() as Promise<LoginResult>
}

async function postJson<T>(path: string): Promise<T> {
  let response: Response
  try {
    response = await fetch(`${API_BASE_URL}${path}`, {
      method: 'POST',
      headers: { Accept: 'application/json', ...authHeaders() },
    })
  } catch (err) {
    throw new ApiError(
      `Could not reach the VARUNA backend at ${API_BASE_URL}${path}. ` +
        `(${err instanceof Error ? err.message : String(err)})`,
    )
  }
  if (!response.ok) {
    let detail = response.statusText
    try {
      const body = await response.json()
      detail = body?.detail ?? body?.message ?? detail
    } catch {
      // not JSON; keep statusText
    }
    if (response.status === 401 || response.status === 403) {
      throw new AuthActionError(detail, response.status)
    }
    throw new ApiError(detail, response.status)
  }
  return response.json() as Promise<T>
}

/** GET /v1/cases/{caseId}/alerts */
export function getCaseAlerts(caseId: string): Promise<{ items: AlertLifecycleRecord[] }> {
  return getJson(`/v1/cases/${encodeURIComponent(caseId)}/alerts`)
}

export function acknowledgeAlert(alertId: string): Promise<AlertLifecycleRecord> {
  return postJson(`/v1/alerts/${encodeURIComponent(alertId)}/acknowledge`)
}

export function escalateAlert(alertId: string): Promise<AlertLifecycleRecord> {
  return postJson(`/v1/alerts/${encodeURIComponent(alertId)}/escalate`)
}

export function resolveAlert(alertId: string): Promise<AlertLifecycleRecord> {
  return postJson(`/v1/alerts/${encodeURIComponent(alertId)}/resolve`)
}

/** GET /v1/cases/{caseId}/operational-summary — alerts + missions + honest
 * per-channel configuration status. */
export function getOperationalSummary(caseId: string): Promise<OperationalSummary> {
  return getJson(`/v1/cases/${encodeURIComponent(caseId)}/operational-summary`)
}

/** The incident PDF URL. Exported for display/debugging only — prefer
 * `downloadReport()`, which surfaces backend errors instead of hiding them. */
export function reportUrl(caseId: string): string {
  return `${API_BASE_URL}/v1/cases/${encodeURIComponent(caseId)}/report`
}

/**
 * Fetch the incident PDF and hand it to the browser as a download.
 *
 * A bare `<a href target="_blank">` was used before, which turned every
 * backend failure into a blank tab or a page of raw JSON — indistinguishable
 * from "the button does nothing". The two real failures this hides are a 404
 * (case never run in this API process) and a 503 (reportlab not installed),
 * both of which the operator needs to see verbatim.
 */
export async function downloadReport(caseId: string): Promise<void> {
  let response: Response
  try {
    response = await fetch(reportUrl(caseId), { headers: { Accept: 'application/pdf' } })
  } catch (err) {
    throw new ApiError(
      `Could not reach the VARUNA backend at ${API_BASE_URL}. ` +
        `(${err instanceof Error ? err.message : String(err)})`,
    )
  }

  if (!response.ok) {
    let detail = response.statusText
    try {
      const body = await response.json()
      detail = body?.detail ?? body?.message ?? detail
    } catch {
      // non-JSON error body; keep statusText
    }
    throw new ApiError(detail, response.status)
  }

  const blob = await response.blob()
  const url = URL.createObjectURL(blob)
  try {
    const a = document.createElement('a')
    a.href = url
    a.download = `VARUNA-incident-${caseId}.pdf`
    document.body.appendChild(a)
    a.click()
    a.remove()
  } finally {
    // Revoke on the next tick so the click has consumed the URL first.
    setTimeout(() => URL.revokeObjectURL(url), 0)
  }
}

/** GET /v1/missions/{missionId}/audit */
export function getMissionAudit(missionId: string): Promise<{ items: Array<Record<string, unknown>> }> {
  return getJson(`/v1/missions/${encodeURIComponent(missionId)}/audit`)
}

/** GET /v1/missions — the live MissionService list (separate store from
 * the replay fixture's OperatorCase.mission — see missions/page.tsx). */
export function listMissions(): Promise<{ items: Array<Record<string, unknown>> }> {
  return getJson('/v1/missions')
}

async function postJsonWithBody<T>(path: string, body: unknown): Promise<T> {
  let response: Response
  try {
    response = await fetch(`${API_BASE_URL}${path}`, {
      method: 'POST',
      headers: { Accept: 'application/json', 'Content-Type': 'application/json', ...authHeaders() },
      body: JSON.stringify(body),
    })
  } catch (err) {
    throw new ApiError(
      `Could not reach the VARUNA backend at ${API_BASE_URL}${path}. ` +
        `(${err instanceof Error ? err.message : String(err)})`,
    )
  }
  if (!response.ok) {
    let detail = response.statusText
    try {
      const respBody = await response.json()
      detail = respBody?.detail ?? respBody?.message ?? detail
    } catch {
      // not JSON
    }
    if (response.status === 401 || response.status === 403) {
      throw new AuthActionError(detail, response.status)
    }
    throw new ApiError(detail, response.status)
  }
  return response.json() as Promise<T>
}

/** POST /v1/missions/{missionId}/approve — genuinely attempts backend
 * authorization. With no login endpoint in this deployment and demo_mode
 * off, this will honestly return 401/403 until a real session exists —
 * see AuthActionError. Never simulated as succeeding client-side. */
export function approveMission(
  missionId: string,
  approvedBy: string,
): Promise<Record<string, unknown>> {
  return postJsonWithBody(`/v1/missions/${encodeURIComponent(missionId)}/approve`, {
    approved_by: approvedBy,
  })
}


// ─────────────── Phase 5: cases, missions FSM, global alerts ───────────────

export interface CaseRow {
  case_id: string
  status: string
  created_at: string
  source: string
  engine_mode: string | null
  validity_state: string | null
  recommendation: string | null
  n_alerts: number
  n_missions: number
  has_operator_view: boolean
}

export interface MissionRow {
  mission_id: string
  case_id: string
  asset_id: string
  state: string
  human_approved_by: string | null
  assigned_at: string | null
  tasking: {
    asset_type?: string
    base_name?: string
    pattern?: string
    flight_hours?: number
    probability_of_detection?: number
    rationale?: string
    launch_time?: string
    search_box?: {
      area_km2?: number
      phi_mass_contained?: number
      center?: { lon: number; lat: number }
      bbox?: { min_lon: number; min_lat: number; max_lon: number; max_lat: number }
    }
  } | null
  [key: string]: unknown
}

/** GET /v1/cases — merged across both repositories, with triage fields. */
export function listCases(): Promise<{ items: CaseRow[]; total: number }> {
  return getJson('/v1/cases')
}

/** POST /v1/cases — RBAC-gated; requires CREATE_CASE. */
export function createCase(caseId?: string): Promise<{ case_id: string; status: string }> {
  return postJsonWithBody('/v1/cases', caseId ? { case_id: caseId } : {})
}

/** GET /v1/alerts — global list with filters. */
export function listAlerts(params: {
  status?: string
  severity?: string
  case_id?: string
  limit?: number
  offset?: number
} = {}): Promise<{
  items: AlertLifecycleRecord[]
  total: number
  limit: number
  offset: number
  returned: number
}> {
  const q = new URLSearchParams()
  for (const [k, v] of Object.entries(params)) {
    if (v !== undefined && v !== null && v !== '') q.set(k, String(v))
  }
  const qs = q.toString()
  return getJson(`/v1/alerts${qs ? `?${qs}` : ''}`)
}

/** GET /v1/cases/{caseId}/missions */
export function listCaseMissions(caseId: string): Promise<{ items: MissionRow[] }> {
  return getJson(`/v1/cases/${encodeURIComponent(caseId)}/missions`)
}

/** GET /v1/missions/{id}/transitions — legal next states, so the UI offers
 * only reachable actions instead of discovering illegality by 409. */
export function missionTransitions(missionId: string): Promise<{
  mission_id: string
  state: string
  legal_next: string[]
  terminal: boolean
}> {
  return getJson(`/v1/missions/${encodeURIComponent(missionId)}/transitions`)
}

/** POST /v1/missions/{id}/transition */
export function transitionMission(
  missionId: string, toState: string, reason?: string,
): Promise<MissionRow> {
  return postJsonWithBody(`/v1/missions/${encodeURIComponent(missionId)}/transition`, {
    to_state: toState, reason: reason ?? null,
  })
}

/** POST /v1/missions/{id}/cancel */
export function cancelMission(missionId: string, reason?: string): Promise<MissionRow> {
  return postJsonWithBody(`/v1/missions/${encodeURIComponent(missionId)}/cancel`, {
    to_state: 'closed', reason: reason ?? null,
  })
}

/** GET /v1/missions/{id}/history — state changes with their reasons. */
export function missionHistory(missionId: string): Promise<{
  mission_id: string
  current_state: string
  human_approved_by: string | null
  assigned_at: string | null
  history: Array<{ state: string; at: string; reason: string | null }>
}> {
  return getJson(`/v1/missions/${encodeURIComponent(missionId)}/history`)
}

/** GET /v1/events?case_id= — the Event Spine, now genuinely visible. */
export function listEvents(caseId?: string): Promise<{
  count: number
  events: Array<{
    event_id: string
    event_type: string
    case_id: string
    actor: string
    timestamp: string
    payload: Record<string, unknown>
  }>
}> {
  return getJson(`/v1/events${caseId ? `?case_id=${encodeURIComponent(caseId)}` : ''}`)
}
