'use client'

/**
 * Asset Management — REAL (Phase 4), backed by GET /v1/assets and
 * GET /v1/personnel.
 *
 * Previously fully mock: hardcoded PATROL_VESSELS/AIRCRAFT arrays, no
 * fetch at all, and deliberately excluded from nav (see lib/mock-data.ts's
 * own "not reachable until wired" policy). That same illustrative data —
 * ICGS Varad/Shaurya/Rajveer, the Dornier/Heron aircraft — is now the real
 * backend seed (packages/varuna_assets/seed.py) instead of a second,
 * disconnected copy living only in this file.
 *
 * SENSORS (satellites, AIS receivers, VTMS) stay static/informational —
 * they aren't assignable response assets in the AssetKind sense, so there
 * is no backend registry for them to be wired to.
 */
import { useCallback, useEffect, useState } from 'react'
import { SectionLabel, StatusBadge, Meter } from '@/components/primitives'
import { Ship, Plane, Satellite, Wrench, Users } from 'lucide-react'
import { type AssetRow, type PersonnelRow, listAssets, listPersonnel } from '@/lib/api'

const SENSORS = [
  { name: 'Sentinel-1A', type: 'SAR (C-band)', operator: 'ESA', status: 'Active', coverage: 100 },
  { name: 'Sentinel-1B', type: 'SAR (C-band)', operator: 'ESA', status: 'Active', coverage: 100 },
  { name: 'RISAT-2B', type: 'SAR (X-band)', operator: 'ISRO', status: 'Active', coverage: 95 },
  { name: 'AIS Rx Mumbai', type: 'AIS Receiver', operator: 'ICG', status: 'Active', coverage: 98 },
  { name: 'AIS Rx Goa', type: 'AIS Receiver', operator: 'ICG', status: 'Active', coverage: 100 },
  { name: 'VTMS Mumbai', type: 'Vessel Traffic', operator: 'Mumbai Port', status: 'Active', coverage: 99 },
]

const VESSEL_KINDS = new Set(['opv', 'fpv', 'interceptor_boat', 'station_boat'])
const AIR_KINDS = new Set(['dornier_228', 'ruav_heron'])

function statusTone(s: string) {
  if (s === 'available') return 'ok' as const
  if (s === 'deployed') return 'saffron' as const
  if (s === 'maintenance') return 'warn' as const
  return 'muted' as const
}

// Illustrative fuel-level proxy from endurance_hours — the seed data has no
// real fuel telemetry (there is none to have), so this is a labelled
// approximation, not a fabricated sensor reading.
function enduranceMeter(hours: number | null, tone: 'teal' | 'saffron') {
  if (hours == null) return <span className="text-[12px] text-muted-foreground">—</span>
  const pct = Math.min(100, Math.round((hours / 240) * 100))
  return (
    <div className="flex items-center gap-2">
      <Meter value={pct} tone={tone} />
      <span className="font-mono text-[11px]">{hours}h</span>
    </div>
  )
}

export default function AssetsPage() {
  const [assets, setAssets] = useState<AssetRow[] | null>(null)
  const [personnel, setPersonnel] = useState<PersonnelRow[] | null>(null)
  const [error, setError] = useState<string | null>(null)

  const load = useCallback(async () => {
    setError(null)
    try {
      const [a, p] = await Promise.all([listAssets(), listPersonnel()])
      setAssets(a.items)
      setPersonnel(p.items)
    } catch (e) {
      setAssets([])
      setPersonnel([])
      setError(e instanceof Error ? e.message : 'Failed to load assets')
    }
  }, [])

  useEffect(() => {
    load()
  }, [load])

  const vessels = (assets ?? []).filter((a) => VESSEL_KINDS.has(a.kind))
  const aircraft = (assets ?? []).filter((a) => AIR_KINDS.has(a.kind))
  const available = (assets ?? []).filter((a) => a.status === 'available').length
  const maintenance = (assets ?? []).filter((a) => a.status === 'maintenance')

  return (
    <>
      <div className="mb-3 flex flex-wrap items-end justify-between gap-2">
        <div>
          <h1 className="text-balance text-xl font-semibold leading-tight tracking-tight text-foreground sm:text-xl">
            Asset Management
          </h1>
          <p className="mt-0.5 font-mono text-[12px] uppercase tracking-[0.1em] text-muted-foreground">
            {assets === null ? 'Loading…' : `${assets.length} asset${assets.length === 1 ? '' : 's'} · live from backend`}
            {' · '}illustrative Indian Coast Guard-style fleet, not a live roster feed
          </p>
        </div>
      </div>

      {error && (
        <p className="mb-3 rounded-sm border border-destructive/40 bg-destructive/5 px-3 py-2 text-[12px] text-destructive">
          {error}
        </p>
      )}

      {/* Summary stats */}
      <div className="grid grid-cols-2 gap-3 sm:grid-cols-4">
        <div className="rounded-sm border border-border bg-card p-3">
          <div className="flex items-center gap-2"><Ship className="h-4 w-4 text-teal" /><span className="font-mono text-[10px] uppercase tracking-[0.12em] text-muted-foreground">Patrol Vessels</span></div>
          <div className="mt-1 font-mono text-[23px] font-bold text-foreground">{vessels.length}</div>
          <div className="font-mono text-[11px] text-muted-foreground">{vessels.filter(v => v.status === 'available').length} available</div>
        </div>
        <div className="rounded-sm border border-border bg-card p-3">
          <div className="flex items-center gap-2"><Plane className="h-4 w-4 text-saffron" /><span className="font-mono text-[10px] uppercase tracking-[0.12em] text-muted-foreground">Aircraft</span></div>
          <div className="mt-1 font-mono text-[23px] font-bold text-foreground">{aircraft.length}</div>
          <div className="font-mono text-[11px] text-muted-foreground">{aircraft.filter(a => a.status === 'available').length} ready</div>
        </div>
        <div className="rounded-sm border border-border bg-card p-3">
          <div className="flex items-center gap-2"><Users className="h-4 w-4 text-[var(--ok)]" /><span className="font-mono text-[10px] uppercase tracking-[0.12em] text-muted-foreground">On-duty personnel</span></div>
          <div className="mt-1 font-mono text-[23px] font-bold text-foreground">{(personnel ?? []).filter(p => p.on_duty).length}</div>
          <div className="font-mono text-[11px] text-muted-foreground">of {(personnel ?? []).length} total</div>
        </div>
        <div className="rounded-sm border border-border bg-card p-3">
          <div className="flex items-center gap-2"><Wrench className="h-4 w-4 text-[var(--warn)]" /><span className="font-mono text-[10px] uppercase tracking-[0.12em] text-muted-foreground">Maintenance</span></div>
          <div className="mt-1 font-mono text-[23px] font-bold text-foreground">{maintenance.length}</div>
          <div className="font-mono text-[11px] text-[var(--warn)]">
            {maintenance.length > 0 ? maintenance.map(m => m.name).join(', ') : 'none'}
          </div>
        </div>
      </div>

      {/* Patrol Vessels */}
      <section className="mt-3 rounded-sm border border-border bg-card p-4">
        <div className="flex items-center gap-2 mb-3"><Ship className="h-4 w-4 text-teal" /><SectionLabel>Patrol Vessels</SectionLabel></div>
        <div className="overflow-x-auto">
          <table className="w-full text-left">
            <thead>
              <tr className="border-b border-border">
                {['Name', 'Kind', 'Base', 'Notes', 'Status', 'Endurance'].map(h => (
                  <th key={h} className="pb-2 pr-4 font-mono text-[10px] font-semibold uppercase tracking-[0.12em] text-muted-foreground">{h}</th>
                ))}
              </tr>
            </thead>
            <tbody>
              {vessels.map(v => (
                <tr key={v.asset_id} className="border-b border-border/50 last:border-b-0">
                  <td className="py-2.5 pr-4 text-[13px] font-semibold text-foreground">{v.name}</td>
                  <td className="py-2.5 pr-4 font-mono text-[12px] text-muted-foreground">{v.kind}</td>
                  <td className="py-2.5 pr-4 text-[13px] text-muted-foreground">{v.home_base}</td>
                  <td className="py-2.5 pr-4 text-[13px] text-muted-foreground">{v.notes ?? '—'}</td>
                  <td className="py-2.5 pr-4"><StatusBadge tone={statusTone(v.status)} dot>{v.status}</StatusBadge></td>
                  <td className="py-2.5 pr-4 w-32">{enduranceMeter(v.endurance_hours, v.status === 'available' ? 'teal' : 'saffron')}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </section>

      {/* Aircraft + Personnel */}
      <div className="mt-3 grid grid-cols-1 gap-3 lg:grid-cols-2">
        <section className="rounded-sm border border-border bg-card p-4">
          <div className="flex items-center gap-2 mb-3"><Plane className="h-4 w-4 text-saffron" /><SectionLabel>Aircraft</SectionLabel></div>
          <div className="space-y-2">
            {aircraft.map(a => (
              <div key={a.asset_id} className="flex items-center justify-between rounded-sm border border-border bg-background/50 p-3">
                <div>
                  <div className="text-[13px] font-semibold text-foreground">{a.name}</div>
                  <div className="text-[12px] text-muted-foreground">{a.kind} · {a.home_base}</div>
                </div>
                <StatusBadge tone={statusTone(a.status)} dot>{a.status}</StatusBadge>
              </div>
            ))}
          </div>
        </section>

        <section className="rounded-sm border border-border bg-card p-4">
          <div className="flex items-center gap-2 mb-3"><Users className="h-4 w-4 text-[var(--ok)]" /><SectionLabel>Duty Personnel</SectionLabel></div>
          <div className="space-y-2">
            {(personnel ?? []).map(p => (
              <div key={p.personnel_id} className="flex items-center justify-between rounded-sm border border-border bg-background/50 p-3">
                <div>
                  <div className="text-[13px] font-semibold text-foreground">{p.name}</div>
                  <div className="text-[12px] text-muted-foreground">{p.rank ?? p.role} · {p.base ?? '—'}</div>
                </div>
                <StatusBadge tone={p.on_duty ? 'ok' : 'muted'} dot>{p.on_duty ? 'on duty' : 'off duty'}</StatusBadge>
              </div>
            ))}
          </div>
        </section>
      </div>

      {/* Sensors — informational only, not an assignable-asset registry */}
      <section className="mt-3 rounded-sm border border-border bg-card p-4">
        <div className="flex items-center gap-2 mb-3">
          <Satellite className="h-4 w-4 text-[var(--ok)]" />
          <SectionLabel>Sensors &amp; Receivers</SectionLabel>
          <span className="font-mono text-[10px] text-muted-foreground">(reference — not part of the mission-assignment asset registry)</span>
        </div>
        <div className="grid grid-cols-1 gap-2 sm:grid-cols-2">
          {SENSORS.map(s => (
            <div key={s.name} className="flex items-center justify-between rounded-sm border border-border bg-background/50 p-3">
              <div>
                <div className="text-[13px] font-semibold text-foreground">{s.name}</div>
                <div className="text-[12px] text-muted-foreground">{s.type} · {s.operator}</div>
              </div>
              <div className="flex items-center gap-2">
                <span className="font-mono text-[11px] text-muted-foreground">{s.coverage}%</span>
                <span className="h-2 w-2 rounded-full bg-[var(--ok)]" />
              </div>
            </div>
          ))}
        </div>
      </section>
    </>
  )
}
