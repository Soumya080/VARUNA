/**
 * Centralized mock data for the Maritime Intelligence System.
 *
 * Everything the UI renders is sourced from this file. When a real backend /
 * model pipeline is available, replace these constants with API calls that
 * return the same shapes — no component should need to change.
 */

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

/** Project a geographic point to overlay percentage coordinates (0–100). */
export function project({ lat, lng }: GeoPoint): { x: number; y: number } {
  const x = ((lng - MAP_BOUNDS.lngMin) / (MAP_BOUNDS.lngMax - MAP_BOUNDS.lngMin)) * 100
  const y = ((MAP_BOUNDS.latMax - lat) / (MAP_BOUNDS.latMax - MAP_BOUNDS.latMin)) * 100
  return { x, y }
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
/* Mission status                                                      */
/* ------------------------------------------------------------------ */

export const MISSION_STATES = [
  'PROPOSED',
  'APPROVAL',
  'DISPATCH',
  'IN PROGRESS',
  'COMPLETED',
  'VERIFIED',
] as const

export type MissionState = (typeof MISSION_STATES)[number]

export const CURRENT_MISSION_STATE: MissionState = 'APPROVAL'

/* ------------------------------------------------------------------ */
/* Navigation                                                          */
/* ------------------------------------------------------------------ */

export const TOP_NAV = [
  'Dashboard',
  'Cases',
  'Alerts',
  'Missions',
  'Assets',
  'Reports',
  'Intelligence',
]

export const CASE_NAV = [
  'Overview',
  'Detection',
  'Source Reconstruction',
  'Vessel Attribution',
  'Assignment & Mission',
  'Evidence Chain',
]

/* ------------------------------------------------------------------ */
/* Route mappings                                                      */
/* ------------------------------------------------------------------ */

/** Sidebar case-section navigation routes */
export const CASE_NAV_ROUTES: Record<string, string> = {
  'Overview': '/',
  'Detection': '/detection',
  'Source Reconstruction': '/source-reconstruction',
  'Vessel Attribution': '/vessel-attribution',
  'Assignment & Mission': '/assignment-mission',
  'Evidence Chain': '/evidence-chain',
}

/** Top-level navigation routes */
export const TOP_NAV_ROUTES: Record<string, string> = {
  'Dashboard': '/',
  'Cases': '/cases',
  'Alerts': '/alerts',
  'Missions': '/missions',
  'Assets': '/assets',
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
  Dashboard: {
    sections: [
      {
        items: [
          {
            label: 'Command Overview',
            description: 'Real-time operational status and KPIs across all active sectors.',
            href: '/',
          },
          {
            label: 'Threat Heatmap',
            description: 'Geospatial threat density overlay for monitored EEZ zones.',
            href: '/',
            badge: 'LIVE',
            tone: 'ok',
          },
          {
            label: 'Watchboard',
            description: 'Priority flagged vessels and entities on active monitoring.',
            href: '/',
            badge: '12 Active',
            tone: 'saffron',
          },
          {
            label: 'System Health',
            description: 'Sensor, model pipeline, and data feed availability status.',
            href: '/',
          },
        ],
      },
    ],
    footer: 'Last dashboard sync · 06:44 UTC',
  },
  Cases: {
    sections: [
      {
        heading: 'Case Management',
        items: [
          {
            label: 'Active Cases',
            description: 'Cases currently under analysis or pending assignment.',
            href: '/cases',
            badge: '4 Active',
            tone: 'saffron',
          },
          {
            label: 'Case Archive',
            description: 'Closed and resolved cases with full evidence chains.',
            href: '/cases',
          },
          {
            label: 'New Case Wizard',
            description: 'Initiate a new investigation from detection or tip-off.',
            href: '/cases',
          },
        ],
      },
      {
        heading: 'Quick Filters',
        items: [
          {
            label: 'Oil Spill / Discharge',
            description: 'Environmental pollution violation cases.',
            href: '/cases',
            badge: '3',
            tone: 'warn',
          },
          {
            label: 'AIS Anomaly',
            description: 'Transponder spoofing or dark-vessel cases.',
            href: '/cases',
          },
          {
            label: 'Unauthorized Entry',
            description: 'EEZ boundary breach and incursion cases.',
            href: '/cases',
          },
        ],
      },
    ],
  },
  Alerts: {
    sections: [
      {
        heading: 'Active Alerts',
        items: [
          {
            label: 'Critical Alerts',
            description: 'High-priority alerts requiring immediate attention.',
            href: '/alerts',
            badge: '2',
            tone: 'destructive',
          },
          {
            label: 'Warning Alerts',
            description: 'Medium-priority alerts for review within 2 hours.',
            href: '/alerts',
            badge: '5',
            tone: 'warn',
          },
          {
            label: 'Informational',
            description: 'Low-priority system and detection notifications.',
            href: '/alerts',
            badge: '18',
            tone: 'muted',
          },
        ],
      },
      {
        heading: 'Configuration',
        items: [
          {
            label: 'Alert Rules',
            description: 'Manage trigger conditions and thresholds.',
            href: '/alerts',
          },
          {
            label: 'Notification Channels',
            description: 'Configure SMS, email, and push notification routing.',
            href: '/alerts',
          },
        ],
      },
    ],
    footer: '2 unread critical alerts',
  },
  Missions: {
    sections: [
      {
        heading: 'Mission Control',
        items: [
          {
            label: 'Active Missions',
            description: 'Currently dispatched or in-progress field missions.',
            href: '/missions',
            badge: '1 In-Flight',
            tone: 'ok',
          },
          {
            label: 'Pending Approval',
            description: 'Missions awaiting authorization from commanding officer.',
            href: '/missions',
            badge: '2 Pending',
            tone: 'warn',
          },
          {
            label: 'Mission History',
            description: 'Completed mission logs with outcomes and after-action reports.',
            href: '/missions',
          },
        ],
      },
      {
        heading: 'Planning',
        items: [
          {
            label: 'Mission Templates',
            description: 'Pre-configured mission profiles for rapid dispatch.',
            href: '/missions',
          },
          {
            label: 'ROE Library',
            description: 'Rules of engagement reference documents.',
            href: '/missions',
          },
        ],
      },
    ],
  },
  Assets: {
    sections: [
      {
        heading: 'Fleet Status',
        items: [
          {
            label: 'Patrol Vessels',
            description: 'Indian Coast Guard and Navy patrol vessel availability.',
            href: '/assets',
            badge: '8 Available',
            tone: 'ok',
          },
          {
            label: 'Aircraft',
            description: 'Maritime surveillance aircraft and UAV status.',
            href: '/assets',
            badge: '3 Ready',
            tone: 'ok',
          },
          {
            label: 'Sensors & Satellites',
            description: 'SAR, optical, and AIS receiver station status.',
            href: '/assets',
          },
        ],
      },
      {
        heading: 'Management',
        items: [
          {
            label: 'Maintenance Schedule',
            description: 'Upcoming and overdue maintenance for assigned assets.',
            href: '/assets',
            badge: '1 Overdue',
            tone: 'warn',
          },
          {
            label: 'Deployment Map',
            description: 'Live positions of all deployed maritime assets.',
            href: '/assets',
          },
        ],
      },
    ],
  },
  Reports: {
    sections: [
      {
        heading: 'Generate',
        items: [
          {
            label: 'Case Report',
            description: 'Full evidence-chain case summary for submission.',
            href: '/reports',
          },
          {
            label: 'Situation Report (SITREP)',
            description: 'Periodic operational summary for command briefing.',
            href: '/reports',
          },
          {
            label: 'Pollution Incident Report',
            description: 'MARPOL-compliant incident documentation.',
            href: '/reports',
          },
        ],
      },
      {
        heading: 'Saved Reports',
        items: [
          {
            label: 'My Reports',
            description: 'Drafted and submitted reports under your account.',
            href: '/reports',
            badge: '7',
            tone: 'muted',
          },
          {
            label: 'Shared with Me',
            description: 'Reports shared by other analysts for review.',
            href: '/reports',
            badge: '3 New',
            tone: 'saffron',
          },
        ],
      },
    ],
  },
  Intelligence: {
    sections: [
      {
        heading: 'Fusion Center',
        items: [
          {
            label: 'Intelligence Feed',
            description: 'Aggregated intelligence from partner agencies and OSINT sources.',
            href: '/intelligence',
            badge: 'LIVE',
            tone: 'ok',
          },
          {
            label: 'Vessel Profiles',
            description: 'Detailed dossiers on vessels of interest and flagged entities.',
            href: '/intelligence',
          },
          {
            label: 'Pattern Analysis',
            description: 'Historical behavior pattern detection and anomaly reports.',
            href: '/intelligence',
          },
        ],
      },
      {
        heading: 'Collaboration',
        items: [
          {
            label: 'Inter-Agency Sharing',
            description: 'Coordinate with DG Shipping, MoEFCC, and partner nations.',
            href: '/intelligence',
          },
          {
            label: 'OSINT Workspace',
            description: 'Open-source intelligence collection and analysis tools.',
            href: '/intelligence',
          },
        ],
      },
    ],
    footer: 'Fusion feed active · 23 sources online',
  },
}
