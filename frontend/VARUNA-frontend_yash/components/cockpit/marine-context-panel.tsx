'use client'

/**
 * Marine Context — honest data-freshness panel (Phase 9, Tier 1).
 *
 * Answers "how fresh is this marine data, actually" from real file
 * metadata (GET /v1/dashboard/marine-context) — deliberately NOT a live
 * feed. ERA5/CMEMS/AIS are all confirmed real-but-archival in this
 * deployment; this panel states each source's actual age honestly rather
 * than implying anything is live. A genuine near-real-time upgrade (a
 * Copernicus Marine NRT product, a live AIS subscription) is a distinct,
 * credentialed future initiative — not something this panel fakes.
 */
import { useEffect, useState } from 'react'
import { Card, Row } from './cockpit-panels'
import { StatusBadge } from '@/components/primitives'
import { API_BASE_URL } from '@/lib/api'

interface FreshnessEntry {
  tier: string
  found: boolean
  file_path: string | null
  data_as_of: string | null
  age_days: number | null
  label: string
}

function tierTone(tier: string): 'ok' | 'warn' | 'muted' {
  if (tier === 'not_configured') return 'muted'
  if (tier === 'reanalysis') return 'warn'
  return 'ok'
}

export function MarineContextPanel() {
  const [data, setData] = useState<Record<string, FreshnessEntry> | null>(null)
  const [err, setErr] = useState<string | null>(null)

  useEffect(() => {
    fetch(`${API_BASE_URL}/v1/dashboard/marine-context`)
      .then((r) => r.json())
      .then(setData)
      .catch((e) => setErr(e instanceof Error ? e.message : 'Failed to load'))
  }, [])

  return (
    <Card title="Marine Context — data freshness (not live)">
      {err && <p className="text-[12px] text-destructive">{err}</p>}
      {!data && !err && <p className="text-[12px] text-muted-foreground">Loading…</p>}
      {data && (
        <div className="space-y-1.5">
          {Object.entries(data).map(([source, entry]) => (
            <div key={source} className="rounded-sm border border-border bg-background/50 px-2 py-1.5">
              <div className="flex items-center justify-between">
                <span className="font-mono text-[12px] font-medium uppercase text-foreground">{source}</span>
                <StatusBadge tone={tierTone(entry.tier)}>{entry.tier.replace(/_/g, ' ')}</StatusBadge>
              </div>
              <p className="mt-0.5 text-[11px] leading-snug text-muted-foreground">{entry.label}</p>
            </div>
          ))}
          <p className="mt-1 text-[10px] leading-snug text-muted-foreground">
            Real local files, real ages — never rounded up to &quot;live.&quot; ERA5 is a
            reanalysis product with an inherent ~5-day latency by design, regardless of
            fetch method.
          </p>
        </div>
      )}
    </Card>
  )
}
