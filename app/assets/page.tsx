'use client'

import { SectionLabel, StatusBadge, Meter } from '@/components/primitives'
import { Ship, Plane, Satellite, Anchor, Wrench, MapPin, Radio, Check } from 'lucide-react'
import { cn } from '@/lib/utils'

const PATROL_VESSELS = [
  { name: 'ICGS Varad', type: 'OPV', base: 'Mumbai', status: 'Deployed', position: 'Arabian Sea — Sector 4A', fuel: 78 },
  { name: 'ICGS Shaurya', type: 'FPV', base: 'Porbandar', status: 'Available', position: 'In port', fuel: 100 },
  { name: 'PV-01 Interceptor', type: 'IB', base: 'Goa', status: 'Available', position: 'In port', fuel: 95 },
  { name: 'PV-03 Interceptor', type: 'IB', base: 'Mumbai Harbor', status: 'Available', position: 'In port', fuel: 92 },
  { name: 'ICGS Rajveer', type: 'OPV', base: 'Kochi', status: 'Deployed', position: 'Lakshadweep Sea', fuel: 64 },
  { name: 'PV-05 Fast Patrol', type: 'FPV', base: 'Chennai', status: 'Maintenance', position: 'In drydock', fuel: 0 },
]

const AIRCRAFT = [
  { name: 'Aircraft-01', type: 'Dornier 228', base: 'INS Hansa, Goa', status: 'Deployed', hours: 2.4 },
  { name: 'Aircraft-02', type: 'Dornier 228', base: 'INS Hansa, Goa', status: 'Available', hours: 0 },
  { name: 'Aircraft-03', type: 'RUAV (Heron)', base: 'Porbandar', status: 'Available', hours: 0 },
]

const SENSORS = [
  { name: 'Sentinel-1A', type: 'SAR (C-band)', operator: 'ESA', status: 'Active', coverage: 100 },
  { name: 'Sentinel-1B', type: 'SAR (C-band)', operator: 'ESA', status: 'Active', coverage: 100 },
  { name: 'RISAT-2B', type: 'SAR (X-band)', operator: 'ISRO', status: 'Active', coverage: 95 },
  { name: 'AIS Rx Mumbai', type: 'AIS Receiver', operator: 'ICG', status: 'Active', coverage: 98 },
  { name: 'AIS Rx Goa', type: 'AIS Receiver', operator: 'ICG', status: 'Active', coverage: 100 },
  { name: 'VTMS Mumbai', type: 'Vessel Traffic', operator: 'Mumbai Port', status: 'Active', coverage: 99 },
]

function statusColor(s: string) {
  if (s === 'Available') return 'ok' as const
  if (s === 'Deployed') return 'saffron' as const
  if (s === 'Active') return 'ok' as const
  return 'warn' as const
}

export default function AssetsPage() {
  return (
    <>
      <div className="mb-3 flex flex-wrap items-end justify-between gap-2">
        <div>
          <h1 className="text-balance text-lg font-semibold leading-tight tracking-tight text-foreground sm:text-xl">
            Asset Management
          </h1>
          <p className="mt-0.5 font-mono text-[11px] uppercase tracking-[0.1em] text-muted-foreground">
            Fleet, aircraft & sensor status · Maritime Intelligence System
          </p>
        </div>
      </div>

      {/* Summary stats */}
      <div className="grid grid-cols-2 gap-3 sm:grid-cols-4">
        <div className="rounded-sm border border-border bg-card p-3">
          <div className="flex items-center gap-2"><Ship className="h-4 w-4 text-teal" /><span className="font-mono text-[9px] uppercase tracking-[0.12em] text-muted-foreground">Patrol Vessels</span></div>
          <div className="mt-1 font-mono text-[22px] font-bold text-foreground">{PATROL_VESSELS.length}</div>
          <div className="font-mono text-[10px] text-muted-foreground">{PATROL_VESSELS.filter(v => v.status === 'Available').length} available</div>
        </div>
        <div className="rounded-sm border border-border bg-card p-3">
          <div className="flex items-center gap-2"><Plane className="h-4 w-4 text-saffron" /><span className="font-mono text-[9px] uppercase tracking-[0.12em] text-muted-foreground">Aircraft</span></div>
          <div className="mt-1 font-mono text-[22px] font-bold text-foreground">{AIRCRAFT.length}</div>
          <div className="font-mono text-[10px] text-muted-foreground">{AIRCRAFT.filter(a => a.status === 'Available').length} ready</div>
        </div>
        <div className="rounded-sm border border-border bg-card p-3">
          <div className="flex items-center gap-2"><Satellite className="h-4 w-4 text-[var(--ok)]" /><span className="font-mono text-[9px] uppercase tracking-[0.12em] text-muted-foreground">Sensors</span></div>
          <div className="mt-1 font-mono text-[22px] font-bold text-foreground">{SENSORS.length}</div>
          <div className="font-mono text-[10px] text-muted-foreground">All active</div>
        </div>
        <div className="rounded-sm border border-border bg-card p-3">
          <div className="flex items-center gap-2"><Wrench className="h-4 w-4 text-[var(--warn)]" /><span className="font-mono text-[9px] uppercase tracking-[0.12em] text-muted-foreground">Maintenance</span></div>
          <div className="mt-1 font-mono text-[22px] font-bold text-foreground">1</div>
          <div className="font-mono text-[10px] text-[var(--warn)]">PV-05 in drydock</div>
        </div>
      </div>

      {/* Patrol Vessels */}
      <section className="mt-3 rounded-sm border border-border bg-card p-4">
        <div className="flex items-center gap-2 mb-3"><Ship className="h-4 w-4 text-teal" /><SectionLabel>Patrol Vessels</SectionLabel></div>
        <div className="overflow-x-auto">
          <table className="w-full text-left">
            <thead>
              <tr className="border-b border-border">
                {['Name', 'Type', 'Base', 'Position', 'Status', 'Fuel'].map(h => (
                  <th key={h} className="pb-2 pr-4 font-mono text-[9px] font-semibold uppercase tracking-[0.12em] text-muted-foreground">{h}</th>
                ))}
              </tr>
            </thead>
            <tbody>
              {PATROL_VESSELS.map(v => (
                <tr key={v.name} className="border-b border-border/50 last:border-b-0">
                  <td className="py-2.5 pr-4 text-[12px] font-semibold text-foreground">{v.name}</td>
                  <td className="py-2.5 pr-4 font-mono text-[11px] text-muted-foreground">{v.type}</td>
                  <td className="py-2.5 pr-4 text-[12px] text-muted-foreground">{v.base}</td>
                  <td className="py-2.5 pr-4 text-[12px] text-muted-foreground">{v.position}</td>
                  <td className="py-2.5 pr-4"><StatusBadge tone={statusColor(v.status)} dot>{v.status}</StatusBadge></td>
                  <td className="py-2.5 pr-4 w-32">{v.fuel > 0 ? <div className="flex items-center gap-2"><Meter value={v.fuel} tone={v.fuel > 50 ? 'teal' : 'saffron'} /><span className="font-mono text-[10px]">{v.fuel}%</span></div> : <span className="text-[11px] text-muted-foreground">—</span>}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </section>

      {/* Aircraft + Sensors */}
      <div className="mt-3 grid grid-cols-1 gap-3 lg:grid-cols-2">
        <section className="rounded-sm border border-border bg-card p-4">
          <div className="flex items-center gap-2 mb-3"><Plane className="h-4 w-4 text-saffron" /><SectionLabel>Aircraft</SectionLabel></div>
          <div className="space-y-2">
            {AIRCRAFT.map(a => (
              <div key={a.name} className="flex items-center justify-between rounded-sm border border-border bg-background/50 p-3">
                <div>
                  <div className="text-[12px] font-semibold text-foreground">{a.name}</div>
                  <div className="text-[11px] text-muted-foreground">{a.type} · {a.base}</div>
                </div>
                <StatusBadge tone={statusColor(a.status)} dot>{a.status}</StatusBadge>
              </div>
            ))}
          </div>
        </section>

        <section className="rounded-sm border border-border bg-card p-4">
          <div className="flex items-center gap-2 mb-3"><Satellite className="h-4 w-4 text-[var(--ok)]" /><SectionLabel>Sensors & Receivers</SectionLabel></div>
          <div className="space-y-2">
            {SENSORS.map(s => (
              <div key={s.name} className="flex items-center justify-between rounded-sm border border-border bg-background/50 p-3">
                <div>
                  <div className="text-[12px] font-semibold text-foreground">{s.name}</div>
                  <div className="text-[11px] text-muted-foreground">{s.type} · {s.operator}</div>
                </div>
                <div className="flex items-center gap-2">
                  <span className="font-mono text-[10px] text-muted-foreground">{s.coverage}%</span>
                  <span className="h-2 w-2 rounded-full bg-[var(--ok)]" />
                </div>
              </div>
            ))}
          </div>
        </section>
      </div>
    </>
  )
}
