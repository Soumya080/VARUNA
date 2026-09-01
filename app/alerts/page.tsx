'use client'

import { SectionLabel, StatusBadge } from '@/components/primitives'
import { AlertTriangle, Bell, BellOff, Check, Clock, MapPin, Ship } from 'lucide-react'
import { cn } from '@/lib/utils'

const ALERTS = [
  { id: 'ALT-2471', type: 'Critical', title: 'AIS transponder gap detected — MT Samudra Prakash', region: 'Arabian Sea', time: '06:12 UTC', detail: '41-minute gap at position 18.93° N, 72.78° E during release window.', read: false },
  { id: 'ALT-2470', type: 'Critical', title: 'Oil slick detected — SAR signature confirmed', region: 'Arabian Sea', time: '06:42 UTC', detail: '14.8 km² slick footprint classified as hydrocarbon with 0.91 confidence.', read: false },
  { id: 'ALT-2469', type: 'Warning', title: 'Unusual speed reduction — MV Western Kaveri', region: 'Arabian Sea', time: '05:55 UTC', detail: 'Speed dropped from 12.3 kn to 4.1 kn near probability field boundary.', read: true },
  { id: 'ALT-2468', type: 'Warning', title: 'EEZ boundary approach — unidentified vessel', region: 'Gulf of Kutch', time: '05:30 UTC', detail: 'Vessel at 22.7° N, 69.1° E heading 340° at 14 kn toward territorial waters.', read: true },
  { id: 'ALT-2467', type: 'Warning', title: 'AIS data quality degradation', region: 'Bay of Bengal', time: '04:20 UTC', detail: 'Reduced AIS coverage in sector 7B — possible atmospheric interference.', read: true },
  { id: 'ALT-2466', type: 'Warning', title: 'Model forcing data delayed', region: 'System', time: '04:00 UTC', detail: 'HYCOM ocean current forecast update delayed by 45 minutes.', read: true },
  { id: 'ALT-2465', type: 'Warning', title: 'Vessel of interest approaching port', region: 'Arabian Sea', time: '03:45 UTC', detail: 'MT Darya No. 8 approaching Mumbai anchorage — ETA 08:30 UTC.', read: true },
  { id: 'ALT-2464', type: 'Info', title: 'Scheduled satellite pass — Sentinel-1', region: 'Arabian Sea', time: '02:30 UTC', detail: 'Next SAR acquisition over AOI scheduled for 18:15 UTC today.', read: true },
  { id: 'ALT-2463', type: 'Info', title: 'Case 24-068 auto-archived', region: 'Indian EEZ', time: '00:00 UTC', detail: 'No activity for 72 hours. Case moved to archive.', read: true },
]

function alertTone(type: string) {
  if (type === 'Critical') return 'destructive' as const
  if (type === 'Warning') return 'warn' as const
  return 'muted' as const
}

export default function AlertsPage() {
  return (
    <>
      <div className="mb-3 flex flex-wrap items-end justify-between gap-2">
        <div>
          <h1 className="text-balance text-lg font-semibold leading-tight tracking-tight text-foreground sm:text-xl">
            Alert Center
          </h1>
          <p className="mt-0.5 font-mono text-[11px] uppercase tracking-[0.1em] text-muted-foreground">
            Real-time alerts · Maritime Intelligence System
          </p>
        </div>
        <div className="flex gap-2">
          <button type="button" className="flex items-center gap-1.5 rounded-sm border border-border bg-card px-3 py-2 text-[12px] text-muted-foreground hover:bg-muted">
            <BellOff className="h-3.5 w-3.5" />
            Mark All Read
          </button>
        </div>
      </div>

      {/* Alert stats */}
      <div className="grid grid-cols-3 gap-3 sm:grid-cols-3">
        {[
          { label: 'Critical', count: ALERTS.filter(a => a.type === 'Critical').length, tone: 'destructive', icon: AlertTriangle },
          { label: 'Warning', count: ALERTS.filter(a => a.type === 'Warning').length, tone: 'warn', icon: Bell },
          { label: 'Informational', count: ALERTS.filter(a => a.type === 'Info').length, tone: 'muted', icon: Bell },
        ].map((s) => (
          <div key={s.label} className="rounded-sm border border-border bg-card p-3">
            <div className="flex items-center gap-2">
              <s.icon className={cn('h-4 w-4', s.tone === 'destructive' ? 'text-destructive' : s.tone === 'warn' ? 'text-[var(--warn)]' : 'text-muted-foreground')} />
              <span className="font-mono text-[9px] uppercase tracking-[0.12em] text-muted-foreground">{s.label}</span>
            </div>
            <div className="mt-1 font-mono text-[22px] font-bold text-foreground">{s.count}</div>
          </div>
        ))}
      </div>

      {/* Alert feed */}
      <div className="mt-3 space-y-2">
        {ALERTS.map((alert) => (
          <section key={alert.id} className={cn(
            'rounded-sm border bg-card p-4 transition-colors',
            !alert.read ? 'border-l-2 border-l-destructive border-t-border border-r-border border-b-border' : 'border-border',
          )}>
            <div className="flex items-start gap-3">
              <AlertTriangle className={cn(
                'h-4 w-4 shrink-0 mt-0.5',
                alert.type === 'Critical' ? 'text-destructive' : alert.type === 'Warning' ? 'text-[var(--warn)]' : 'text-muted-foreground',
              )} />
              <div className="min-w-0 flex-1">
                <div className="flex items-center gap-2 flex-wrap">
                  <span className="text-[13px] font-semibold text-foreground">{alert.title}</span>
                  <StatusBadge tone={alertTone(alert.type)}>{alert.type}</StatusBadge>
                  {!alert.read && <span className="h-2 w-2 rounded-full bg-destructive" />}
                </div>
                <p className="mt-1 text-[12px] text-muted-foreground">{alert.detail}</p>
                <div className="mt-2 flex items-center gap-4 text-[11px] text-muted-foreground">
                  <span className="flex items-center gap-1"><Clock className="h-3 w-3" />{alert.time}</span>
                  <span className="flex items-center gap-1"><MapPin className="h-3 w-3" />{alert.region}</span>
                  <span className="font-mono text-[10px]">{alert.id}</span>
                </div>
              </div>
            </div>
          </section>
        ))}
      </div>
    </>
  )
}
