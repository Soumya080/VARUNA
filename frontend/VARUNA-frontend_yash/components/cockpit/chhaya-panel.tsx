'use client'

/**
 * CHHAYA v2 — vessel intelligence over REAL MC20 Sentinel-1 tiles.
 * Every value here comes from `GET /v1/chhaya/investigate/{tile}`; the panel
 * never invents a candidate, a score, or an outcome.
 */
import { useCallback, useEffect, useState } from 'react'
import { StatusBadge } from '@/components/primitives'
import { Card, Row } from './cockpit-panels'
import { API_BASE_URL } from '@/lib/api'

interface Candidate {
  candidate_id: string
  position: { lon: number; lat: number } | null
  geolocation_valid: boolean
  vessel_score: number
  score_type: string
  detector_source: string
}

interface Handoff {
  outcome: string
  outcome_reason: string
  detector_source: string
  detector_mode: string
  detector_available: boolean
  candidates: Candidate[]
  _input: {
    tile_id: string
    tile_shape: number[]
    sensor: string | null
    n_ais_positions_in_tile: number
    detector_note: string
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
      title="CHHAYA — Vessel intelligence (real Sentinel-1)"
      id="chhaya-v2"
      right={
        data ? (
          <StatusBadge tone={OUTCOME_TONE[data.outcome] ?? 'muted'}>
            {data.outcome.replace(/_/g, ' ')}
          </StatusBadge>
        ) : undefined
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
          <Row label="Detector" value={`${data.detector_source} (${data.detector_mode})`} />
          <Row label="Tile" value={`${data._input.tile_shape.join('×')} px`} />
          <Row label="Sensor" value={data._input.sensor ?? '—'} />
          <Row label="AIS positions in tile" value={data._input.n_ais_positions_in_tile} />
          <Row label="Candidates" value={data.candidates.length} />

          <p className="text-[11px] leading-snug text-muted-foreground">{data.outcome_reason}</p>

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
                  className="flex items-center gap-2 rounded-sm border border-border bg-background/50 px-2 py-1 text-[11px]"
                >
                  <StatusBadge tone={c.geolocation_valid ? 'ok' : 'warn'}>
                    {c.geolocation_valid ? 'geo ok' : 'geo invalid'}
                  </StatusBadge>
                  <span className="font-mono text-foreground">
                    {c.position
                      ? `${c.position.lat.toFixed(4)}, ${c.position.lon.toFixed(4)}`
                      : '—'}
                  </span>
                  <span className="ml-auto font-mono text-muted-foreground">
                    score {c.vessel_score?.toFixed(2)}
                  </span>
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
