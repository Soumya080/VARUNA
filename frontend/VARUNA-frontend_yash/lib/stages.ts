/**
 * The canonical 13-stage pipeline, grouped into 9 readable acts — Phase 7
 * (docs/product/HONESTY_LEDGER.md #22).
 *
 * Replaces the decorative `STORY` array that used to live in
 * `app/page.tsx` (`['OBSERVE','DETECT','LOCALIZE','FORECAST','ATTRIBUTE',
 * 'ASSESS','RECOMMEND','AUTHORIZE','RECORD']` — 9 chips, identical classes,
 * referencing no real state). These 13 stage keys and their grouping into
 * acts are NOT invented: they mirror `apps/api/routers/run_stream.py
 * ::_PIPELINE_STAGE` / `STAGE_ORDER` exactly, the real backend vocabulary
 * already used by `components/cockpit/cockpit-panels.tsx::RunTimeline`.
 * This file is the single place both the story strip and the timeline
 * should read stage identity/labels/grouping from, so they can never again
 * drift into two different vocabularies.
 */

export type StageKey =
  | 'DATA' | 'NETRA' | 'DETECTION_EVIDENCE' | 'STARTING_POINT' | 'PRATIVARTAN'
  | 'PRAVAAH' | 'CHHAYA' | 'NYAYA' | 'VALIDITY' | 'NEXT_BEST_ACTION'
  | 'ALERT' | 'MISSION' | 'PRAMAN'

export const STAGE_ORDER: StageKey[] = [
  'DATA', 'NETRA', 'DETECTION_EVIDENCE', 'STARTING_POINT', 'PRATIVARTAN',
  'PRAVAAH', 'CHHAYA', 'NYAYA', 'VALIDITY', 'NEXT_BEST_ACTION',
  'ALERT', 'MISSION', 'PRAMAN',
]

export const STAGE_LABEL: Record<StageKey, string> = {
  DATA: 'Data / forcing',
  NETRA: 'NETRA detection',
  DETECTION_EVIDENCE: 'Detection evidence',
  STARTING_POINT: 'Starting point',
  PRATIVARTAN: 'PRATIVARTAN (Φ)',
  PRAVAAH: 'PRAVAAH forecast',
  CHHAYA: 'CHHAYA hypotheses',
  NYAYA: 'NYAYA attribution',
  VALIDITY: 'Validity gate',
  NEXT_BEST_ACTION: 'Next best action',
  ALERT: 'Alert',
  MISSION: 'Mission',
  PRAMAN: 'PRAMAN provenance',
}

export interface Act {
  id: string
  label: string
  stages: StageKey[]
  href: string
}

/**
 * 9 acts, each a real destination (Phase 9's story pages / existing
 * routes) rather than a decorative label — clicking a chip navigates
 * there. This IS the "procedural flow" ask: order here is the order a
 * judge should read the case.
 */
export const ACTS: Act[] = [
  { id: 'observe', label: 'Observe', stages: ['DATA'], href: '/detection' },
  { id: 'detect', label: 'Detect', stages: ['NETRA', 'DETECTION_EVIDENCE'], href: '/detection' },
  { id: 'localize', label: 'Localize', stages: ['STARTING_POINT', 'PRATIVARTAN'], href: '/source-reconstruction' },
  { id: 'forecast', label: 'Forecast', stages: ['PRAVAAH'], href: '/source-reconstruction' },
  { id: 'attribute', label: 'Attribute', stages: ['CHHAYA', 'NYAYA'], href: '/vessel-attribution' },
  { id: 'assess', label: 'Assess', stages: ['VALIDITY'], href: '/evidence-chain' },
  { id: 'decide', label: 'Decide', stages: ['NEXT_BEST_ACTION'], href: '/intelligence' },
  { id: 'act', label: 'Act', stages: ['ALERT', 'MISSION'], href: '/missions' },
  { id: 'record', label: 'Record', stages: ['PRAMAN'], href: '/reports' },
]

export function actForStage(stage: StageKey): Act | undefined {
  return ACTS.find((a) => a.stages.includes(stage))
}
