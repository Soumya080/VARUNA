'use client'

/**
 * CHHAYA v2 — vessel intelligence over REAL MC20 Sentinel-1 tiles.
 * Every value here comes from `GET /v1/chhaya/investigate/{tile}`; the panel
 * never invents a candidate, a score, or an outcome.
 */
import { useCallback, useEffect, useState } from 'react'
import { InfoTip, Meter, StatusBadge } from '@/components/primitives'
import { Card, Row } from './cockpit-panels'
import { API_BASE_URL } from '@/lib/api'
import { isWithinFrame, projectToBBox, type LonLatBBox } from '@/lib/geo-projection'

/**
 * Mirrors `packages/varuna_chhaya/v2/nyaya_handoff.py::CandidateEvidenceRecord`
 * field-for-field — this is what the wire actually sends. The previous
 * version of this interface (`vessel_score`/`score_type`/`detector_source`
 * per-candidate, none of which exist on the wire) was silently masked
 * because `candidates` was always empty in practice; the first real
 * detection would have crashed this panel live (Phase 5B fix, see
 * docs/product/HONESTY_LEDGER.md).
 */
interface Candidate {
  candidate_id: string
  sar_vessel_score: number
  sar_score_type: string
  ais_state: string
  ais_distance_km: number | null
  origin_spatial_consistency: number | null
  origin_temporal_consistency: number | null
  course_consistency: number | null
  speed_consistency: number | null
  relative_plausibility: number
  rank: number
  missing_evidence: string[]
  position: { lon: number; lat: number } | null
  geolocation_valid: boolean
  geolocation_rejection_reason: string | null
}

interface Handoff {
  outcome: string
  outcome_reason: string
  detector_source: string
  detector_mode: string
  detector_available: boolean
  coverage_quality: number | null
  candidates: Candidate[]
  missing_evidence: string[]
  _input: {
    tile_id: string
    tile_shape: number[]
    tile_bbox: LonLatBBox
    sensor: string | null
    n_ais_positions_in_tile: number
    ais_positions: Array<{ lon: number; lat: number }>
    detector_note: string
    corridor_recurrence: { count: number; radius_km: number } | null
    suitability: {
      suitable_for_cfar: boolean
      peak_sigma_above_mean: number
      threshold_sigma: number
      reason: string
    } | null
  }
}

const OUTCOME_TONE: Record<string, 'ok' | 'warn' | 'destructive' | 'muted'> = {
  known_vessel: 'ok',
  possible_dark_vessel: 'destructive',
  inconclusive: 'warn',
  inconclusive_ais_coverage: 'warn',
  no_supported_vessel: 'muted',
  sar_evidence_unavailable: 'muted',
  invalid_geolocation: 'warn',
}

/**
 * Tile-context mini-map (Phase 1). A plain inline SVG, not Leaflet — this
 * panel lives in a narrow rail and every value plotted here is real backend
 * data (candidate/AIS positions), never a fabricated basemap. Points outside
 * the tile bbox by more than a small tolerance are shown at the frame's edge
 * with a dashed marker rather than silently clipped, so an operator can see
 * "this candidate's geolocation put it off-tile" instead of nothing.
 */
function TileMiniMap({
  bbox,
  candidates,
  aisPositions,
}: {
  bbox: LonLatBBox
  candidates: Candidate[]
  aisPositions: Array<{ lon: number; lat: number }>
}) {
  const clamp = (v: number) => Math.max(2, Math.min(98, v))

  return (
    <svg
      viewBox="0 0 100 100"
      className="h-32 w-full rounded-sm border border-border bg-background"
      role="img"
      aria-label="Tile candidate and AIS position map"
    >
      <rect x={0.5} y={0.5} width={99} height={99} fill="none" stroke="var(--border)" strokeWidth={0.5} />
      {/* AIS positions: small teal dots, drawn first so candidates sit on top */}
      {aisPositions.map((p, i) => {
        const proj = projectToBBox(p.lon, p.lat, bbox)
        if (!isWithinFrame(proj)) return null
        return (
          <circle
            key={`ais-${i}`}
            cx={clamp(proj.x)}
            cy={clamp(proj.y)}
            r={1.1}
            fill="var(--teal)"
            opacity={0.75}
          />
        )
      })}
      {/* Candidates: colored/shaped by geolocation validity + outcome tone */}
      {candidates.map((c) => {
        if (!c.position) return null
        const proj = projectToBBox(c.position.lon, c.position.lat, bbox)
        const outside = !isWithinFrame(proj)
        const color = !c.geolocation_valid
          ? 'var(--destructive)'
          : 'var(--saffron)'
        return (
          <circle
            key={c.candidate_id}
            cx={clamp(proj.x)}
            cy={clamp(proj.y)}
            r={2}
            fill={color}
            stroke={outside ? color : 'none'}
            strokeDasharray={outside ? '1,1' : undefined}
            strokeWidth={outside ? 0.8 : 0}
          />
        )
      })}
      {candidates.length === 0 && aisPositions.length === 0 && (
        <text x={50} y={52} textAnchor="middle" fontSize={5} fill="var(--muted-foreground)">
          no plottable positions
        </text>
      )}
    </svg>
  )
}

export function ChhayaPanelV2() {
  const [tiles, setTiles] = useState<Array<{ tile_id: string }>>([])
  const [tileId, setTileId] = useState<string | null>(null)
  const [data, setData] = useState<Handoff | null>(null)
  const [err, setErr] = useState<string | null>(null)
  const [loading, setLoading] = useState(false)

  useEffect(() => {
    fetch(`${API_BASE_URL}/v1/chhaya/tiles`)
      .then((r) => r.json())
      .then((d) => {
        if (d.available) {
          setTiles(d.tiles)
          setTileId(d.tiles[0]?.tile_id ?? null)
        } else {
          setErr(d.reason)
        }
      })
      .catch((e) => setErr(String(e)))
  }, [])

  const investigate = useCallback(async (tid: string) => {
    setLoading(true)
    setErr(null)
    try {
      const r = await fetch(`${API_BASE_URL}/v1/chhaya/investigate/${encodeURIComponent(tid)}`)
      if (!r.ok) throw new Error(`HTTP ${r.status}`)
      setData(await r.json())
    } catch (e) {
      setData(null)
      setErr(e instanceof Error ? e.message : 'CHHAYA request failed')
    } finally {
      setLoading(false)
    }
  }, [])

  return (
    <Card
      title="CHHAYA · Vessel Evidence (SAR tile)"
      id="chhaya-v2"
      right={
        <>
          <InfoTip label="Two stages of one question: CHHAYA · Source Hypothesis asks 'what kind of source is this?' (per case). CHHAYA · Vessel Evidence asks 'which vessel?' (per SAR tile, from real Sentinel-1 imagery). Not the same computation." />
          {data && (
            <StatusBadge tone={OUTCOME_TONE[data.outcome] ?? 'muted'}>
              {data.outcome.replace(/_/g, ' ')}
            </StatusBadge>
          )}
        </>
      }
    >
      {err && <p className="text-[12px] text-destructive">{err}</p>}

      <div className="flex flex-wrap items-center gap-1.5">
        <select
          value={tileId ?? ''}
          onChange={(e) => setTileId(e.target.value)}
          className="rounded-sm border border-border bg-background px-2 py-1 font-mono text-[11px] text-foreground"
        >
          {tiles.map((t) => (
            <option key={t.tile_id} value={t.tile_id}>
              {t.tile_id}
            </option>
          ))}
        </select>
        <button
          type="button"
          disabled={!tileId || loading}
          onClick={() => tileId && investigate(tileId)}
          className="rounded-sm bg-primary px-2.5 py-1 text-[11px] font-semibold uppercase tracking-[0.08em] text-primary-foreground hover:bg-[var(--navy-muted)] disabled:opacity-40"
        >
          {loading ? 'Running…' : 'Investigate tile'}
        </button>
      </div>

      {data && (
        <div className="mt-2 space-y-1.5 border-t border-border pt-2">
          {data._input.tile_bbox && (
            <TileMiniMap
              bbox={data._input.tile_bbox}
              candidates={data.candidates}
              aisPositions={data._input.ais_positions ?? []}
            />
          )}

          <Row label="Detector" value={`${data.detector_source} (${data.detector_mode})`} />
          <Row label="Tile" value={`${data._input.tile_shape.join('×')} px`} />
          <Row label="Sensor" value={data._input.sensor ?? '—'} />
          <Row label="AIS positions in tile" value={data._input.n_ais_positions_in_tile} />
          <Row label="Candidates" value={data.candidates.length} />
          {data.coverage_quality != null && (
            <Row label="Coverage quality" value={data.coverage_quality.toFixed(2)} />
          )}
          {data.missing_evidence.length > 0 && (
            <Row
              label="Missing evidence"
              value={<span className="text-[10px]">{data.missing_evidence.join(', ')}</span>}
            />
          )}
          {data._input.corridor_recurrence && (
            <Row
              label={`Prior cases within ${data._input.corridor_recurrence.radius_km}km`}
              value={
                <span title="From SMRITI — advisory context only, never a detection factor">
                  {data._input.corridor_recurrence.count}
                </span>
              }
            />
          )}

          <p className="text-[11px] leading-snug text-muted-foreground">{data.outcome_reason}</p>

          {data._input.suitability && (
            <div className="space-y-1">
              <div className="flex items-center justify-between text-[10px] text-muted-foreground">
                <span>Peak signal vs. CFAR threshold</span>
                <span className="font-mono tabular-nums">
                  {data._input.suitability.peak_sigma_above_mean.toFixed(1)}σ /{' '}
                  {data._input.suitability.threshold_sigma.toFixed(1)}σ
                </span>
              </div>
              <Meter
                value={(data._input.suitability.peak_sigma_above_mean /
                  data._input.suitability.threshold_sigma) * 100}
                tone={data._input.suitability.suitable_for_cfar ? 'teal' : 'saffron'}
              />
            </div>
          )}

          {data._input.suitability && !data._input.suitability.suitable_for_cfar && (
            <div className="rounded-sm border border-[color-mix(in_oklch,var(--warn)_45%,transparent)] bg-[color-mix(in_oklch,var(--warn)_9%,transparent)] px-2 py-1.5">
              <div className="font-mono text-[10px] font-semibold uppercase tracking-[0.1em] text-[color-mix(in_oklch,var(--warn)_55%,black)]">
                Imagery unsuitable for vessel CFAR
              </div>
              <p className="mt-1 text-[11px] leading-snug text-muted-foreground">
                {data._input.suitability.reason}
              </p>
            </div>
          )}

          {data.candidates.length > 0 && (
            <ul className="space-y-1">
              {data.candidates.slice(0, 8).map((c) => (
                <li
                  key={c.candidate_id}
                  className="space-y-1 rounded-sm border border-border bg-background/50 px-2 py-1.5 text-[11px]"
                >
                  <div className="flex items-center gap-2">
                    <span className="font-mono text-muted-foreground">#{c.rank}</span>
                    <StatusBadge tone={c.geolocation_valid ? 'ok' : 'warn'}>
                      {c.geolocation_valid ? 'geo ok' : 'geo invalid'}
                    </StatusBadge>
                    <span className="font-mono text-foreground">
                      {c.position
                        ? `${c.position.lat.toFixed(4)}, ${c.position.lon.toFixed(4)}`
                        : '—'}
                    </span>
                    <span className="ml-auto font-mono text-muted-foreground">
                      plausibility {c.relative_plausibility.toFixed(2)}
                    </span>
                  </div>
                  <div className="flex flex-wrap items-center gap-x-3 gap-y-0.5 font-mono text-[10px] text-muted-foreground">
                    <span>SAR {c.sar_score_type} {c.sar_vessel_score.toFixed(2)}</span>
                    <span>AIS {c.ais_state.replace(/_/g, ' ')}</span>
                    {c.ais_distance_km != null && <span>{c.ais_distance_km.toFixed(1)}km</span>}
                  </div>
                  {!c.geolocation_valid && c.geolocation_rejection_reason && (
                    <p className="text-[10px] leading-snug text-[color-mix(in_oklch,var(--warn)_55%,black)]">
                      geolocation rejected: {c.geolocation_rejection_reason}
                    </p>
                  )}
                  {c.missing_evidence.length > 0 && (
                    <p className="text-[10px] leading-snug text-muted-foreground">
                      missing: {c.missing_evidence.join(', ')}
                    </p>
                  )}
                </li>
              ))}
            </ul>
          )}

          <p className="text-[10px] leading-snug text-muted-foreground">
            {data._input.detector_note}
          </p>
          <p className="text-[10px] leading-snug text-[color-mix(in_oklch,var(--warn)_55%,black)]">
            Scores are <strong>relative plausibility</strong>, not calibrated probabilities.
          </p>
        </div>
      )}
    </Card>
  )
}
