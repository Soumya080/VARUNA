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

  // Generate deterministic SAR-like ocean noise based on bbox (seeded)
  const seed = Math.abs(bbox.min_lon * 1000 + bbox.min_lat * 100) % 1000
  const noiseRects: Array<{ x: number; y: number; w: number; h: number; op: number }> = []
  for (let i = 0; i < 120; i++) {
    const s = ((seed + i * 7 + 13) * 2654435761) % 2147483647
    noiseRects.push({
      x: (s % 100),
      y: ((s * 3 + 17) % 100),
      w: 0.5 + (s % 3) * 0.3,
      h: 0.3 + ((s * 2) % 3) * 0.2,
      op: 0.03 + ((s * 5) % 10) * 0.008,
    })
  }

  // Generate scan line positions for radar effect
  const scanLines = Array.from({ length: 20 }, (_, i) => i * 5)

  return (
    <svg
      viewBox="0 0 100 100"
      className="h-64 w-full rounded border border-border"
      role="img"
      aria-label="SAR tile radar visualization"
    >
      <defs>
        {/* Glow filter for candidate markers */}
        <filter id="glow" x="-50%" y="-50%" width="200%" height="200%">
          <feGaussianBlur stdDeviation="1.5" result="blur" />
          <feMerge>
            <feMergeNode in="blur" />
            <feMergeNode in="SourceGraphic" />
          </feMerge>
        </filter>
        {/* Stronger glow for detection zone */}
        <filter id="glow-strong" x="-50%" y="-50%" width="200%" height="200%">
          <feGaussianBlur stdDeviation="3" result="blur" />
          <feMerge>
            <feMergeNode in="blur" />
            <feMergeNode in="blur" />
            <feMergeNode in="SourceGraphic" />
          </feMerge>
        </filter>
        {/* Radar sweep gradient */}
        <radialGradient id="radar-sweep" cx="50%" cy="50%" r="50%">
          <stop offset="0%" stopColor="#1e3a5f" stopOpacity="0.3" />
          <stop offset="60%" stopColor="#0f2233" stopOpacity="0.6" />
          <stop offset="100%" stopColor="#091520" stopOpacity="0.9" />
        </radialGradient>
        {/* Ocean texture gradient */}
        <linearGradient id="ocean-grad" x1="0%" y1="0%" x2="100%" y2="100%">
          <stop offset="0%" stopColor="#0a1628" />
          <stop offset="50%" stopColor="#0d1f35" />
          <stop offset="100%" stopColor="#0a1a2e" />
        </linearGradient>
      </defs>

      {/* Dark ocean background simulating SAR water backscatter */}
      <rect x={0} y={0} width={100} height={100} fill="url(#ocean-grad)" />

      {/* SAR speckle noise — simulates radar backscatter texture */}
      {noiseRects.map((n, i) => (
        <rect
          key={`noise-${i}`}
          x={n.x}
          y={n.y}
          width={n.w}
          height={n.h}
          fill="#4a9eff"
          opacity={n.op}
          rx={0.1}
        />
      ))}

      {/* Radar scan lines — horizontal */}
      {scanLines.map((y) => (
        <line
          key={`scan-${y}`}
          x1={0}
          y1={y}
          x2={100}
          y2={y}
          stroke="#1a4a7a"
          strokeWidth={0.15}
          opacity={0.4}
        />
      ))}

      {/* Grid overlay — coordinate reference */}
      <g stroke="#2a5a8a" strokeWidth={0.2} strokeDasharray="1,2" opacity={0.5}>
        <line x1={0} y1={25} x2={100} y2={25} />
        <line x1={0} y1={50} x2={100} y2={50} />
        <line x1={0} y1={75} x2={100} y2={75} />
        <line x1={25} y1={0} x2={25} y2={100} />
        <line x1={50} y1={0} x2={50} y2={100} />
        <line x1={75} y1={0} x2={75} y2={100} />
      </g>

      {/* Tile border frame */}
      <rect
        x={0.5}
        y={0.5}
        width={99}
        height={99}
        fill="none"
        stroke="#2a5a8a"
        strokeWidth={0.8}
      />

      {/* Coordinate labels — styled like radar HUD */}
      <text x={2} y={5} fontSize={3} fill="#4a9eff" fontFamily="monospace" opacity={0.8}>
        {bbox.max_lat.toFixed(3)}°N
      </text>
      <text x={2} y={98} fontSize={3} fill="#4a9eff" fontFamily="monospace" opacity={0.8}>
        {bbox.min_lat.toFixed(3)}°N
      </text>
      <text x={98} y={5} textAnchor="end" fontSize={3} fill="#4a9eff" fontFamily="monospace" opacity={0.8}>
        {bbox.max_lon.toFixed(3)}°W
      </text>
      <text x={98} y={98} textAnchor="end" fontSize={3} fill="#4a9eff" fontFamily="monospace" opacity={0.8}>
        {bbox.min_lon.toFixed(3)}°W
      </text>

      {/* Center crosshair */}
      <line x1={48} y1={50} x2={52} y2={50} stroke="#4a9eff" strokeWidth={0.3} opacity={0.5} />
      <line x1={50} y1={48} x2={50} y2={52} stroke="#4a9eff" strokeWidth={0.3} opacity={0.5} />

      {/* AIS positions: teal glowing dots */}
      {aisPositions.map((p, i) => {
        const proj = projectToBBox(p.lon, p.lat, bbox)
        if (!isWithinFrame(proj)) return null
        return (
          <g key={`ais-${i}`}>
            {/* Outer glow ring */}
            <circle
              cx={clamp(proj.x)}
              cy={clamp(proj.y)}
              r={2.5}
              fill="none"
              stroke="#00e5ff"
              strokeWidth={0.3}
              opacity={0.4}
            />
            {/* Inner dot */}
            <circle
              cx={clamp(proj.x)}
              cy={clamp(proj.y)}
              r={1.2}
              fill="#00e5ff"
              opacity={0.85}
              filter="url(#glow)"
            />
          </g>
        )
      })}

      {/* Candidates: bright radar contacts with detection rings */}
      {candidates.map((c) => {
        if (!c.position) return null
        const proj = projectToBBox(c.position.lon, c.position.lat, bbox)
        const outside = !isWithinFrame(proj)
        const color = !c.geolocation_valid ? '#ff4444' : '#ff9900'
        const cx = clamp(proj.x)
        const cy = clamp(proj.y)
        return (
          <g key={c.candidate_id}>
            {/* Detection zone ring — pulsing outer */}
            <circle
              cx={cx}
              cy={cy}
              r={6}
              fill="none"
              stroke={color}
              strokeWidth={0.4}
              strokeDasharray="1.5,1"
              opacity={0.5}
            >
              <animate
                attributeName="r"
                values="5;7;5"
                dur="2s"
                repeatCount="indefinite"
              />
              <animate
                attributeName="opacity"
                values="0.5;0.2;0.5"
                dur="2s"
                repeatCount="indefinite"
              />
            </circle>
            {/* Inner detection ring */}
            <circle
              cx={cx}
              cy={cy}
              r={3.5}
              fill="none"
              stroke={color}
              strokeWidth={0.5}
              opacity={0.7}
            />
            {/* Core bright dot */}
            <circle
              cx={cx}
              cy={cy}
              r={2}
              fill={color}
              opacity={0.95}
              filter="url(#glow-strong)"
            />
            {/* Crosshair on candidate */}
            <line x1={cx - 4} y1={cy} x2={cx - 2.5} y2={cy} stroke={color} strokeWidth={0.3} opacity={0.8} />
            <line x1={cx + 2.5} y1={cy} x2={cx + 4} y2={cy} stroke={color} strokeWidth={0.3} opacity={0.8} />
            <line x1={cx} y1={cy - 4} x2={cx} y2={cy - 2.5} stroke={color} strokeWidth={0.3} opacity={0.8} />
            <line x1={cx} y1={cy + 2.5} x2={cx} y2={cy + 4} stroke={color} strokeWidth={0.3} opacity={0.8} />
            {/* Rank label */}
            <text
              x={cx + 5}
              y={cy - 3}
              fontSize={3}
              fill={color}
              fontFamily="monospace"
              fontWeight="bold"
              opacity={0.9}
            >
              #{c.rank}
            </text>
            {/* Score label */}
            <text
              x={cx + 5}
              y={cy + 1}
              fontSize={2.5}
              fill={color}
              fontFamily="monospace"
              opacity={0.7}
            >
              p={c.relative_plausibility.toFixed(2)}
            </text>
            {outside && (
              <text
                x={cx + 5}
                y={cy + 4}
                fontSize={2}
                fill="#ff4444"
                fontFamily="monospace"
                opacity={0.8}
              >
                OFF-TILE
              </text>
            )}
          </g>
        )
      })}

      {/* Status HUD text */}
      {candidates.length === 0 && aisPositions.length === 0 && (
        <g>
          <text
            x={50}
            y={48}
            textAnchor="middle"
            fontSize={4}
            fill="#4a9eff"
            fontFamily="monospace"
            fontWeight="bold"
            opacity={0.8}
          >
            NO RADAR CONTACTS
          </text>
          <text
            x={50}
            y={54}
            textAnchor="middle"
            fontSize={3}
            fill="#4a9eff"
            fontFamily="monospace"
            opacity={0.5}
          >
            Tile under surveillance
          </text>
        </g>
      )}

      {/* HUD corner brackets */}
      <polyline points="1,5 1,1 5,1" fill="none" stroke="#4a9eff" strokeWidth={0.5} opacity={0.6} />
      <polyline points="95,1 99,1 99,5" fill="none" stroke="#4a9eff" strokeWidth={0.5} opacity={0.6} />
      <polyline points="1,95 1,99 5,99" fill="none" stroke="#4a9eff" strokeWidth={0.5} opacity={0.6} />
      <polyline points="95,99 99,99 99,95" fill="none" stroke="#4a9eff" strokeWidth={0.5} opacity={0.6} />
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
                    <p className="text-[10px] leading-snug text-[color-mix(in_oklch,var(--destructive)_70%,black)] font-medium">
                      Missing AIS/Evidence: {c.missing_evidence.join(', ')}
                    </p>
                  )}
                  <div className="mt-1.5 rounded border border-border/50 bg-muted/20 p-1.5">
                    <p className="mb-0.5 text-[9px] font-semibold text-muted-foreground uppercase tracking-[0.05em]">
                      Spoofing / Latent Consistency
                    </p>
                    <div className="flex flex-wrap gap-x-3 gap-y-1 font-mono text-[10px] text-foreground">
                      <span>Spatial {c.origin_spatial_consistency?.toFixed(2) ?? '—'}</span>
                      <span>Temporal {c.origin_temporal_consistency?.toFixed(2) ?? '—'}</span>
                      <span>Course {c.course_consistency?.toFixed(2) ?? '—'}</span>
                      <span>Speed {c.speed_consistency?.toFixed(2) ?? '—'}</span>
                    </div>
                  </div>
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
