/**
 * Centralized mock data for the VARUNA.
 *
 * Everything the UI renders is sourced from this file. When a real backend /
 * model pipeline is available, replace these constants with API calls that
 * return the same shapes — no component should need to change.
 */
import { projectToBBox } from './geo-projection'

/* ------------------------------------------------------------------ */
/* Geographic projection                                               */
/* ------------------------------------------------------------------ */

/**
 * Bounding box of the operational map view. Used to project geographic
 * coordinates onto the 0–100 overlay space that sits on top of the
 * satellite basemap image. A real MapLibre/Mapbox layer would replace this.
 */
export const MAP_BOUNDS = {
  lngMin: 68,
  lngMax: 74,
  latMin: 15.5,
  latMax: 21.5,
}

export interface GeoPoint {
  lat: number
  lng: number
}

/** Project a geographic point to overlay percentage coordinates (0–100).
 * Delegates to the shared `lib/geo-projection.ts` math (Phase 1) so this
 * mock-only helper and real-data panels never drift onto two formulas. */
export function project({ lat, lng }: GeoPoint): { x: number; y: number } {
  return projectToBBox(lng, lat, {
    min_lon: MAP_BOUNDS.lngMin, max_lon: MAP_BOUNDS.lngMax,
    min_lat: MAP_BOUNDS.latMin, max_lat: MAP_BOUNDS.latMax,
  })
}

export function formatLat(lat: number): string {
  return `${Math.abs(lat).toFixed(3)}° ${lat >= 0 ? 'N' : 'S'}`
}

export function formatLng(lng: number): string {
  return `${Math.abs(lng).toFixed(3)}° ${lng >= 0 ? 'E' : 'W'}`
}

/* ------------------------------------------------------------------ */
/* Case                                                                */
/* ------------------------------------------------------------------ */

export type CaseStatus = 'ACTIVE ANALYSIS' | 'ANALYSIS' | 'REVIEW' | 'CLOSED'

export interface CaseRecord {
  id: string
  region: string
  status: CaseStatus
}

export const ACTIVE_CASE: CaseRecord = {
  id: 'CASE 24-071',
  region: 'Arabian Sea',
  status: 'ACTIVE ANALYSIS',
}

export const OTHER_CASES: CaseRecord[] = [
  { id: 'CASE 24-070', region: 'Gulf of Kutch', status: 'ANALYSIS' },
  { id: 'CASE 24-069', region: 'Bay of Bengal', status: 'REVIEW' },
  { id: 'CASE 24-068', region: 'Indian EEZ', status: 'CLOSED' },
]

/* ------------------------------------------------------------------ */
/* Top summary strip                                                   */
/* ------------------------------------------------------------------ */

export interface SummaryMetric {
  label: string
  primary: string
  secondary?: string
  tone?: 'default' | 'ok' | 'warn' | 'saffron'
}

export const CASE_SUMMARY: SummaryMetric[] = [
  { label: 'Observation', primary: '06:42 UTC', secondary: '12 JUN 2024' },
  { label: 'Drift Window', primary: '38.5 h', secondary: 'reverse advection' },
  {
    label: 'Reconstructed Origin',
    primary: '18.936° N',
    secondary: '72.762° E',
    tone: 'saffron',
  },
  { label: 'Confidence', primary: '0.87', secondary: 'HIGH', tone: 'ok' },
  { label: 'Validity Gate', primary: 'PASSED', secondary: 'evidence valid', tone: 'ok' },
]

/* ------------------------------------------------------------------ */
/* Map: slick observation                                              */
/* ------------------------------------------------------------------ */

/** Irregular slick polygon, expressed in geographic coordinates. */
export const SLICK_POLYGON: GeoPoint[] = [
  { lat: 19.02, lng: 72.5 },
  { lat: 19.05, lng: 72.58 },
  { lat: 19.0, lng: 72.66 },
  { lat: 18.95, lng: 72.63 },
  { lat: 18.9, lng: 72.68 },
  { lat: 18.86, lng: 72.6 },
  { lat: 18.9, lng: 72.52 },
  { lat: 18.96, lng: 72.48 },
]

export const SLICK_INFO = {
  label: 'SLICK OBSERVATION',
  observedUtc: '06:42 UTC',
  area: '14.8 km²',
  distanceFromCoast: '17.2 km',
  estimatedAge: '24 ± 6 h',
  sensor: 'SAR — Sentinel-1 C-band',
  confidence: 'High (0.91)',
  center: { lat: 18.96, lng: 72.58 } as GeoPoint,
}

/* ------------------------------------------------------------------ */
/* Map: source probability field                                       */
/* ------------------------------------------------------------------ */

export const ORIGIN = {
  point: { lat: 18.936, lng: 72.762 } as GeoPoint,
  peakLikelihood: 64.2,
  estimatedRelease: '12 JUN · 16:30 UTC ± 2 h',
  radiusKm: 9.5,
  method: 'Adjoint back-trajectory ensemble (n=4,000)',
}

/* ------------------------------------------------------------------ */
/* Map: particle trajectories (reverse advection)                      */
/* ------------------------------------------------------------------ */

/** Each trajectory is a list of points running origin -> observed slick. */
export const PARTICLE_TRAJECTORIES: GeoPoint[][] = [
  [
    { lat: 18.936, lng: 72.762 },
    { lat: 18.95, lng: 72.7 },
    { lat: 18.97, lng: 72.64 },
    { lat: 18.98, lng: 72.58 },
  ],
  [
    { lat: 18.936, lng: 72.762 },
    { lat: 18.92, lng: 72.7 },
    { lat: 18.93, lng: 72.62 },
    { lat: 18.95, lng: 72.55 },
  ],
  [
    { lat: 18.936, lng: 72.762 },
    { lat: 18.97, lng: 72.72 },
    { lat: 19.0, lng: 72.66 },
    { lat: 19.01, lng: 72.57 },
  ],
  [
    { lat: 18.936, lng: 72.762 },
    { lat: 18.9, lng: 72.71 },
    { lat: 18.89, lng: 72.63 },
    { lat: 18.9, lng: 72.55 },
  ],
  [
    { lat: 18.936, lng: 72.762 },
    { lat: 18.955, lng: 72.73 },
    { lat: 18.985, lng: 72.68 },
    { lat: 18.995, lng: 72.61 },
  ],
]

/* ------------------------------------------------------------------ */
/* Map: candidate vessels + AIS tracks                                 */
/* ------------------------------------------------------------------ */

export interface Vessel {
  id: string
  name: string
  type: string
  flag: string
  imo: string
  rank: number
  role: 'PRIMARY LEAD' | 'ALTERNATE' | 'SECONDARY'
  attributionScore: number // percentage
  position: GeoPoint
  lastSeenUtc: string
  speedKn: number
  headingDeg: number
  /** AIS track polyline in geographic coordinates. */
  track: GeoPoint[]
  notes: string
}

export const VESSELS: Vessel[] = [
  {
    id: 'v1',
    name: 'MT Samudra Prakash',
    type: 'Product Tanker',
    flag: 'India',
    imo: 'IMO 9483217',
    rank: 1,
    role: 'PRIMARY LEAD',
    attributionScore: 68,
    position: { lat: 18.9, lng: 72.79 },
    lastSeenUtc: '05:58 UTC',
    speedKn: 11.4,
    headingDeg: 208,
    track: [
      { lat: 19.08, lng: 72.86 },
      { lat: 19.0, lng: 72.83 },
      { lat: 18.95, lng: 72.8 },
      { lat: 18.9, lng: 72.79 },
    ],
    notes:
      'Transited within 1.6 km of reconstructed origin during the estimated release window. AIS gap of 41 minutes recorded at 16:12 UTC.',
  },
  {
    id: 'v2',
    name: 'MV Western Kaveri',
    type: 'Bulk Carrier',
    flag: 'Panama',
    imo: 'IMO 9611430',
    rank: 2,
    role: 'ALTERNATE',
    attributionScore: 21,
    position: { lat: 19.06, lng: 72.7 },
    lastSeenUtc: '06:20 UTC',
    speedKn: 9.1,
    headingDeg: 155,
    track: [
      { lat: 19.25, lng: 72.64 },
      { lat: 19.16, lng: 72.66 },
      { lat: 19.1, lng: 72.69 },
      { lat: 19.06, lng: 72.7 },
    ],
    notes:
      'Crossed the northern edge of the probability field. Continuous AIS coverage; no discharge-consistent maneuvers observed.',
  },
  {
    id: 'v3',
    name: 'MT Darya No. 8',
    type: 'Chemical Tanker',
    flag: 'Marshall Is.',
    imo: 'IMO 9702551',
    rank: 3,
    role: 'SECONDARY',
    attributionScore: 7,
    position: { lat: 18.8, lng: 72.66 },
    lastSeenUtc: '04:47 UTC',
    speedKn: 13.2,
    headingDeg: 342,
    track: [
      { lat: 18.62, lng: 72.58 },
      { lat: 18.7, lng: 72.61 },
      { lat: 18.76, lng: 72.64 },
      { lat: 18.8, lng: 72.66 },
    ],
    notes:
      'Peripheral track south of the probability field. Timing marginally inconsistent with the estimated release window.',
  },
]

/* ------------------------------------------------------------------ */
/* Right panel: source estimate + recommended action                   */
/* ------------------------------------------------------------------ */

export const RECOMMENDED_ACTION =
  'Request discharge log and establish chain-of-custody review for the leading vessel track.'

/* ------------------------------------------------------------------ */
/* Right panel: evidence health                                        */
/* ------------------------------------------------------------------ */

export interface EvidenceMetric {
  label: string
  value: number
}

export const EVIDENCE_HEALTH = {
  overall: 96,
  metrics: [
    { label: 'SAR Data', value: 100 },
    { label: 'AIS Data', value: 98 },
    { label: 'Model Consistency', value: 95 },
    { label: 'Forcing Data', value: 95 },
  ] as EvidenceMetric[],
}

/* ------------------------------------------------------------------ */
/* Analytical pipeline                                                 */
/* ------------------------------------------------------------------ */

export type PipelineStatus = 'Completed' | 'Passed' | 'Pending Approval'

export interface PipelineStage {
  id: string
  index: string
  title: string
  status: PipelineStatus
  detail: string
  outputs: { label: string; value: string }[]
}

export const PIPELINE: PipelineStage[] = [
  {
    id: 'detection',
    index: '01',
    title: 'Detection',
    status: 'Completed',
    detail:
      'SAR imagery classified for oil-slick signatures. Slick footprint segmented and area computed.',
    outputs: [
      { label: 'Sensor', value: 'Sentinel-1 SAR' },
      { label: 'Area', value: '14.8 km²' },
      { label: 'Confidence', value: '0.91' },
    ],
  },
  {
    id: 'backtrack',
    index: '02',
    title: 'Backtrack',
    status: 'Completed',
    detail:
      'Reverse advection driven by ocean-current and wind forcing over the 38.5-hour drift window.',
    outputs: [
      { label: 'Drift window', value: '38.5 h' },
      { label: 'Ensemble', value: '4,000 particles' },
      { label: 'Forcing', value: 'HYCOM + GFS' },
    ],
  },
  {
    id: 'origin',
    index: '03',
    title: 'Origin Field',
    status: 'Completed',
    detail:
      'Back-trajectory ensemble aggregated into a spatial likelihood field for the release location.',
    outputs: [
      { label: 'Peak likelihood', value: '64.2%' },
      { label: 'Centroid', value: '18.936° N, 72.762° E' },
      { label: 'Release', value: '16:30 UTC ± 2 h' },
    ],
  },
  {
    id: 'attribution',
    index: '04',
    title: 'Attribution',
    status: 'Completed',
    detail:
      'AIS tracks intersected against the origin field and release window to score candidate vessels.',
    outputs: [
      { label: 'Candidates', value: '3 vessels' },
      { label: 'Leading score', value: '68%' },
      { label: 'Method', value: 'Spatiotemporal overlap' },
    ],
  },
  {
    id: 'validity',
    index: '05',
    title: 'Validity Gate',
    status: 'Passed',
    detail:
      'Automated evidence checks on data coverage, model consistency and forcing quality.',
    outputs: [
      { label: 'Evidence health', value: '96%' },
      { label: 'Coverage', value: 'Complete' },
      { label: 'Result', value: 'Passed' },
    ],
  },
  {
    id: 'assignment',
    index: '06',
    title: 'Assignment',
    status: 'Pending Approval',
    detail:
      'Recommended inspection assets and mission windows generated. Awaiting authorization.',
    outputs: [
      { label: 'Primary asset', value: 'Aircraft-02' },
      { label: 'Window', value: '10:30–11:15 UTC' },
      { label: 'State', value: 'Pending auth' },
    ],
  },
]

/* ------------------------------------------------------------------ */
/* Assignment & mission table                                          */
/* ------------------------------------------------------------------ */

export interface Assignment {
  id: string
  candidate: string
  recommendation: 'PRIMARY LEAD' | 'ALTERNATE'
  asset: string
  task: string
  priority: 'HIGH' | 'MEDIUM' | 'LOW'
  window: string
  status: 'PENDING AUTH' | 'AUTHORIZED' | 'DISPATCHED'
}

export const ASSIGNMENTS: Assignment[] = [
  {
    id: 'a1',
    candidate: 'MT Samudra Prakash',
    recommendation: 'PRIMARY LEAD',
    asset: 'Aircraft-02',
    task: 'Inspection / Overflight',
    priority: 'HIGH',
    window: '10:30–11:15 UTC',
    status: 'PENDING AUTH',
  },
  {
    id: 'a2',
    candidate: 'MV Western Kaveri',
    recommendation: 'ALTERNATE',
    asset: 'Patrol Vessel-03',
    task: 'Monitoring',
    priority: 'MEDIUM',
    window: '10:45–12:00 UTC',
    status: 'PENDING AUTH',
  },
]

/* ------------------------------------------------------------------ */
/* Feasibility summary                                                 */
/* ------------------------------------------------------------------ */

export interface FeasibilityItem {
  label: string
  value: string
  feasible: boolean
}

export const FEASIBILITY: FeasibilityItem[] = [
  { label: 'Distance', value: '34 km', feasible: true },
  { label: 'Asset Availability', value: 'Available', feasible: true },
  { label: 'Weather', value: 'Acceptable', feasible: true },
  { label: 'Mission Window', value: 'Valid', feasible: true },
  { label: 'Evidence Validity', value: 'Passed', feasible: true },
]

/* ------------------------------------------------------------------ */
/* Mission status — Phase 6A (docs/product/HONESTY_LEDGER.md #18):     */
/* the fake linear MISSION_STATES/CURRENT_MISSION_STATE track that      */
/* used to live here is deleted outright. components/mission-fsm.tsx    */
/* renders the REAL 13-state branching FSM instead, driven by           */
/* GET /v1/missions/{id}/transitions and /history.                      */
/* ------------------------------------------------------------------ */
/* Navigation                                                          */
/* ------------------------------------------------------------------ */

export const TOP_NAV = [
  'Dashboard',
  'Cases',
  'Alerts',
  'Missions',
  'Assignment',
  // Phase 11 fix (docs/product/HONESTY_LEDGER.md #29): TOP_NAV_ROUTES
  // below already mapped 'Assets' -> /assets and /assets already reads
  // real data (GET /v1/assets, /v1/personnel) — but 'Assets' was never
  // added to THIS array, the one header.tsx actually renders, so the page
  // stayed unreachable from the header despite being real.
  'Assets',
  // Phase 9 made both real (docs/product/HONESTY_LEDGER.md #26); the
  // other 4 real story pages live under the Dashboard dropdown's Case
  // section instead of flat here, to keep this bar from growing to 12
  // items.
  'Reports',
  'Intelligence',
] as const

export const CASE_NAV = [
  'Overview',
  'Assignment & Mission',
] as const

/* ------------------------------------------------------------------ */
/* Route mappings                                                      */
/* ------------------------------------------------------------------ */

/** Sidebar case-section navigation routes */
/**
 * Case-level sub-navigation. Detection / Source Reconstruction /
 * Vessel Attribution / Evidence Chain are still mock pages, so they are
 * not routed. The cockpit Overview already shows all of that data from
 * the real OperatorCase.
 */
export const CASE_NAV_ROUTES: Record<string, string> = {
  'Overview': '/',
  'Assignment & Mission': '/assignment-mission',
}

/** Top-level navigation routes */
/**
 * Only routes that are genuinely backend-driven appear in the nav.
 *
 * All 6 story pages (Detection, Source Reconstruction, Vessel Attribution,
 * Evidence Chain, Intelligence, Reports), Assets, and every OPS route are
 * real as of Phase 9/4 (docs/product/HONESTY_LEDGER.md #26/#29) — a
 * reviewer who clicks any nav item now sees real OperatorCase data, never
 * a fabricated vessel name or invented percentage. Detection/Source
 * Reconstruction/Vessel Attribution/Evidence Chain are reachable via the
 * "Dashboard" dropdown's Case section rather than as flat top-level items
 * — 12 flat items would defeat the point of grouping the procedure.
 */
export const TOP_NAV_ROUTES: Record<string, string> = {
  'Dashboard': '/',
  'Cases': '/cases',
  'Alerts': '/alerts',
  'Missions': '/missions',
  'Assignment': '/assignment-mission',
  // Phase 4: real now (GET /v1/assets, /v1/personnel) — added to nav per
  // this file's own documented policy above (only genuinely backend-driven
  // routes belong here).
  'Assets': '/assets',
  // Phase 9 converted these from hardcoded mocks to real OperatorCase data
  // (docs/product/HONESTY_LEDGER.md #26) — no longer "still hardcoded mock
  // pages" per this file's own former note. Reachable via the "Dashboard"
  // dropdown's Case section above, and now genuinely routable here too.
  'Reports': '/reports',
  'Intelligence': '/intelligence',
}

/* ------------------------------------------------------------------ */
/* Navigation dropdown menus                                           */
/* ------------------------------------------------------------------ */

export interface NavMenuItem {
  label: string
  description: string
  href: string
  badge?: string
  tone?: 'ok' | 'warn' | 'saffron' | 'muted' | 'destructive'
}

export interface NavMenuSection {
  heading?: string
  items: NavMenuItem[]
}

export interface NavMenuData {
  sections: NavMenuSection[]
  footer?: string
}

export const NAV_MENUS: Record<string, NavMenuData> = {
  // Phase 11 fix (docs/product/HONESTY_LEDGER.md #29): this menu was
  // entirely fabricated — a fake "LIVE" badge, a fake "12 Active" count, a
  // hardcoded stale timestamp footer, and every item pointing at `/`
  // regardless of label. Replaced with the real CASE procedure: the 6
  // story pages Phase 9 converted to real data, in the same order as the
  // cockpit's own story spine (`lib/stages.ts`), plus the cockpit itself.
  Dashboard: {
    sections: [
      {
        heading: 'Case',
        items: [
          { label: 'Cockpit Overview', description: "The case's full composed view — map, evidence, mission, alerts.", href: '/' },
          { label: 'Detection', description: "NETRA's real SAR classification for this case.", href: '/detection' },
          { label: 'Source Reconstruction', description: 'PRATIVARTAN backward reconstruction — diagnostics and sensitivity.', href: '/source-reconstruction' },
          { label: 'Vessel Attribution', description: 'NYAYA attribution — computed result and historical context, never conflated.', href: '/vessel-attribution' },
          { label: 'Intelligence', description: 'Source hypothesis, uncertainty, decision trace, SMRITI memory.', href: '/intelligence' },
          { label: 'Evidence Chain', description: 'The real evidence lineage graph, verification ledger, provenance.', href: '/evidence-chain' },
          { label: 'Reports', description: 'Generate the real PDF incident report for this case.', href: '/reports' },
        ],
      },
    ],
  },
  // Phase 11 fix (docs/product/HONESTY_LEDGER.md #29): found while fixing
  // Dashboard/Reports/Intelligence above — this menu (and Alerts/Missions/
  // Assets below) had the same problem at larger scale: fabricated badge
  // counts presented as live numbers ("4 Active", "3", "1 Overdue", ...),
  // fake sub-features ("New Case Wizard", "ROE Library"), and a fake
  // "2 unread critical alerts" footer. Numeric badges are the most
  // misleading kind of fabrication here — a specific number reads as a
  // live measurement. Removed; items now point at their real page, which
  // shows the real count directly rather than duplicating a stale one in
  // a dropdown.
  Cases: {
    sections: [
      {
        items: [
          { label: 'All Cases', description: 'Every case from every real store, unified — the actual GET /v1/cases list.', href: '/cases' },
        ],
      },
    ],
  },
  Alerts: {
    sections: [
      {
        items: [
          { label: 'Alert Center', description: 'Real alerts for the active case, with acknowledge/escalate/resolve wired to the backend.', href: '/alerts' },
        ],
      },
    ],
  },
  Missions: {
    sections: [
      {
        items: [
          { label: 'Mission Control', description: 'Real missions from MissionService, each with its actual 13-state FSM graph.', href: '/missions' },
        ],
      },
    ],
  },
  Assets: {
    sections: [
      {
        items: [
          { label: 'Fleet & Personnel', description: 'Real asset and personnel records — GET /v1/assets, /v1/personnel.', href: '/assets' },
        ],
      },
    ],
  },
  // Phase 11 fix (docs/product/HONESTY_LEDGER.md #29): this menu offered
  // 3 fabricated report "types" (all pointing at the same page anyway), a
  // fake "MARPOL-compliant" claim, and a fake saved-reports list with fake
  // badge counts ("7", "3 New"). VARUNA has exactly one real report
  // mechanism — see /reports's own page docstring.
  Reports: {
    sections: [
      {
        items: [
          {
            label: 'Incident Report (PDF)',
            description: "The one real report VARUNA generates — built fresh from a case's own evidence at request time. No saved-report history is kept.",
            href: '/reports',
          },
        ],
      },
    ],
  },
  // Phase 11 fix (docs/product/HONESTY_LEDGER.md #29): this menu invented
  // a fake "LIVE" intelligence feed, fake vessel dossiers, fake OSINT
  // tooling, and a fake "23 sources online" footer — none of which VARUNA
  // has. Replaced with what /intelligence actually shows: CHHAYA source
  // hypothesis, uncertainty, decision trace, SMRITI memory.
  Intelligence: {
    sections: [
      {
        items: [
          { label: 'Source Hypothesis', description: "CHHAYA's declared-likelihood-ratio reasoning for this case, with the full factor waterfall.", href: '/intelligence' },
          { label: 'Uncertainty', description: 'OOD risk and every uncertainty component, never collapsed to one number.', href: '/intelligence' },
          { label: 'Decision Trace', description: "The agentic loop's real, executed steps — not a chat log.", href: '/intelligence' },
          { label: 'SMRITI Memory', description: 'Similar past cases retrieved for context — advisory only.', href: '/intelligence' },
        ],
      },
    ],
  },
}
