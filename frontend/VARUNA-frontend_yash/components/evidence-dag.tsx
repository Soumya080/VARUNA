'use client'

/**
 * Evidence lineage DAG — Phase 10A (docs/product/HONESTY_LEDGER.md #15).
 *
 * `oc.intelligence.evidence_lineage` is a real dependency graph (typically
 * ~12 nodes for a composed case) — `depends_on`/`contradicts`/
 * `superseded_by` — shown everywhere else in this app only as a flat
 * count. This renders it as a hand-rolled layered SVG (no graph library —
 * a dozen nodes doesn't justify one), laid out left-to-right with the
 * x-axis mapped onto the SAME 13-stage vocabulary
 * `lib/stages.ts`/`RunTimeline` already use, so the data-flow diagram and
 * the procedural story strip share one axis rather than inventing a
 * second stage vocabulary.
 *
 * `EvidenceKind` (forcing/detection/ais/origin/...) doesn't map 1:1 onto
 * the 13 pipeline `StageKey`s — it's a coarser, evidence-provenance
 * vocabulary, not a stage identity. `KIND_TO_STAGE` below is a best-effort
 * LAYOUT mapping (which column a kind's evidence visually belongs near),
 * not a claim that e.g. "ais" IS the "DETECTION_EVIDENCE" stage.
 *
 * `contradicts` edges render in the destructive tone — most systems hide
 * disagreement between evidence items; this surfaces it.
 */
import { useState } from 'react'
import type { EvidenceLedgerItem } from '@/lib/operator-case-types'
import { STAGE_ORDER, STAGE_LABEL, type StageKey } from '@/lib/stages'
import { InfoTip } from '@/components/primitives'

const KIND_TO_STAGE: Record<string, StageKey> = {
  forcing: 'DATA',
  detection: 'NETRA',
  ais: 'DETECTION_EVIDENCE',
  origin: 'PRATIVARTAN',
  source_hypothesis: 'CHHAYA',
  attribution: 'NYAYA',
  forecast: 'PRAVAAH',
  validity: 'VALIDITY',
  uncertainty: 'VALIDITY',
  data_quality: 'DETECTION_EVIDENCE',
  memory: 'NYAYA',
  decision: 'NEXT_BEST_ACTION',
  operator: 'MISSION',
}

const COL_W = 92
const ROW_H = 30
const R = 6
const PAD_X = 16
const PAD_TOP = 16

export function EvidenceDag({ lineage }: { lineage: EvidenceLedgerItem[] }) {
  const [selected, setSelected] = useState<string | null>(null)

  if (lineage.length === 0) {
    return <p className="text-[11px] text-muted-foreground">No evidence lineage recorded for this case.</p>
  }

  // Column = mapped stage index. Row = stacking order within that column
  // (stable: appearance order in the lineage array, which is itself
  // recorded chronologically).
  const columnCounts: Record<string, number> = {}
  const positioned = lineage.map((item) => {
    const stage = KIND_TO_STAGE[item.kind] ?? 'PRAMAN'
    const col = STAGE_ORDER.indexOf(stage)
    const row = columnCounts[stage] ?? 0
    columnCounts[stage] = row + 1
    return { item, col, row, stage }
  });

  const byId = new Map(positioned.map((p) => [p.item.evidence_id, p]))
  const maxRows = Math.max(1, ...Object.values(columnCounts))
  const usedCols = new Set(positioned.map((p) => p.col))
  const width = PAD_X * 2 + (Math.max(...usedCols, 0) + 1) * COL_W
  const height = PAD_TOP + 22 + maxRows * ROW_H + 10

  function centerOf(p: { col: number; row: number }) {
    return { cx: PAD_X + p.col * COL_W + COL_W / 2, cy: PAD_TOP + 22 + p.row * ROW_H + ROW_H / 2 }
  }

  const selectedItem = selected ? byId.get(selected) : null
  const highlightIds = new Set<string>()
  if (selectedItem) {
    highlightIds.add(selectedItem.item.evidence_id)
    for (const d of selectedItem.item.depends_on) highlightIds.add(d)
    for (const c of selectedItem.item.contradicts ?? []) highlightIds.add(c)
  }

  return (
    <div className="space-y-2">
      <div className="overflow-x-auto scroll-thin">
        <svg viewBox={`0 0 ${width} ${height}`} width={width} height={height} role="img" aria-label="Evidence lineage graph">
          {/* Stage column headers, sharing the story-spine's own labels */}
          {[...usedCols].map((col) => (
            <text
              key={col}
              x={PAD_X + col * COL_W + COL_W / 2}
              y={12}
              textAnchor="middle"
              fontSize={7}
              className="fill-muted-foreground font-mono uppercase tracking-[0.04em]"
            >
              {STAGE_LABEL[STAGE_ORDER[col]].split(' ')[0]}
            </text>
          ))}

          {/* depends_on edges */}
          {positioned.map((p) =>
            p.item.depends_on.map((depId) => {
              const dep = byId.get(depId)
              if (!dep) return null
              const a = centerOf(dep)
              const b = centerOf(p)
              const dim = selectedItem && !(highlightIds.has(p.item.evidence_id) && highlightIds.has(depId))
              return (
                <line
                  key={`${p.item.evidence_id}-dep-${depId}`}
                  x1={a.cx} y1={a.cy} x2={b.cx} y2={b.cy}
                  stroke="var(--border)"
                  strokeWidth={dim ? 0.75 : 1.5}
                  opacity={dim ? 0.35 : 1}
                />
              )
            }),
          )}

          {/* contradicts edges — destructive tone, dashed */}
          {positioned.map((p) =>
            (p.item.contradicts ?? []).map((cid) => {
              const other = byId.get(cid)
              if (!other) return null
              const a = centerOf(p)
              const b = centerOf(other)
              return (
                <line
                  key={`${p.item.evidence_id}-contra-${cid}`}
                  x1={a.cx} y1={a.cy} x2={b.cx} y2={b.cy}
                  stroke="var(--destructive)"
                  strokeWidth={1.5}
                  strokeDasharray="2,2"
                />
              )
            }),
          )}

          {/* nodes */}
          {positioned.map((p) => {
            const { cx, cy } = centerOf(p)
            const isSelected = selected === p.item.evidence_id
            const dim = selectedItem && !highlightIds.has(p.item.evidence_id)
            return (
              <g
                key={p.item.evidence_id}
                onClick={() => setSelected(isSelected ? null : p.item.evidence_id)}
                style={{ cursor: 'pointer' }}
                opacity={dim ? 0.35 : 1}
              >
                <circle
                  cx={cx} cy={cy} r={R}
                  fill={p.item.mode === 'real' ? 'var(--ok)' : p.item.mode === 'simulated' ? 'var(--saffron)' : 'var(--muted)'}
                  stroke={isSelected ? 'var(--foreground)' : 'none'}
                  strokeWidth={isSelected ? 1.5 : 0}
                />
                <text x={cx} y={cy + R + 8} textAnchor="middle" fontSize={6.5} className="fill-muted-foreground font-mono">
                  {p.item.kind.slice(0, 8)}
                </text>
              </g>
            )
          })}
        </svg>
      </div>

      {selectedItem ? (
        <div className="rounded-sm border border-border bg-background/50 p-2.5 text-[11px]">
          <div className="flex items-center gap-1.5">
            <span className="font-mono font-semibold text-foreground">{selectedItem.item.evidence_id}</span>
            <InfoTip label="Click any node to inspect it; click again to deselect. Highlighted edges show what this item depends on and what it contradicts." />
          </div>
          <p className="mt-1 text-foreground/90">{selectedItem.item.summary}</p>
          <p className="mt-1 font-mono text-[10px] text-muted-foreground">
            produced by {selectedItem.item.produced_by} · mode {selectedItem.item.mode}
            {selectedItem.item.confidence != null && ` · confidence ${(selectedItem.item.confidence * 100).toFixed(0)}%`}
          </p>
          {selectedItem.item.depends_on.length > 0 && (
            <p className="mt-1 text-[10px] text-muted-foreground">depends on: {selectedItem.item.depends_on.join(', ')}</p>
          )}
          {(selectedItem.item.contradicts?.length ?? 0) > 0 && (
            <p className="mt-1 text-[10px] text-destructive">contradicts: {selectedItem.item.contradicts!.join(', ')}</p>
          )}
        </div>
      ) : (
        <p className="text-[10px] text-muted-foreground">Click a node to inspect its provenance and dependencies.</p>
      )}
    </div>
  )
}
