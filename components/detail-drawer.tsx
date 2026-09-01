'use client'

import {
  ORIGIN,
  SLICK_INFO,
  VESSELS,
  formatLat,
  formatLng,
} from '@/lib/mock-data'
import { cn } from '@/lib/utils'
import { Droplets, Ship, Target, X } from 'lucide-react'
import type { ReactNode } from 'react'
import type { MapDetail } from './map/map-utils'
import { Meter, StatusBadge } from './primitives'

function Field({ label, value }: { label: string; value: ReactNode }) {
  return (
    <div className="rounded-sm border border-border bg-muted/30 px-3 py-2">
      <div className="font-mono text-[9px] uppercase tracking-[0.1em] text-muted-foreground">
        {label}
      </div>
      <div className="mt-0.5 font-mono text-[13px] font-medium text-foreground">{value}</div>
    </div>
  )
}

function DrawerShell({
  icon,
  eyebrow,
  title,
  onClose,
  children,
}: {
  icon: ReactNode
  eyebrow: string
  title: string
  onClose: () => void
  children: ReactNode
}) {
  return (
    <>
      <div
        className="fixed inset-0 z-50 bg-black/40 animate-in fade-in duration-150"
        onClick={onClose}
        aria-hidden="true"
      />
      <div
        role="dialog"
        aria-modal="true"
        aria-label={title}
        className="fixed inset-y-0 right-0 z-50 flex w-full max-w-md flex-col border-l border-border bg-card shadow-2xl animate-in slide-in-from-right duration-200"
      >
        <div className="flex items-start justify-between gap-3 border-b border-border bg-muted/40 px-4 py-3">
          <div className="flex items-center gap-2.5">
            <span className="grid h-9 w-9 place-items-center rounded-sm bg-primary text-primary-foreground">
              {icon}
            </span>
            <div>
              <div className="font-mono text-[9px] uppercase tracking-[0.14em] text-muted-foreground">
                {eyebrow}
              </div>
              <h2 className="text-[15px] font-semibold leading-tight text-foreground">{title}</h2>
            </div>
          </div>
          <button
            type="button"
            onClick={onClose}
            className="grid h-8 w-8 place-items-center rounded-sm text-muted-foreground transition-colors hover:bg-muted hover:text-foreground"
            aria-label="Close details"
          >
            <X className="h-4 w-4" />
          </button>
        </div>
        <div className="flex-1 overflow-y-auto scroll-thin p-4">{children}</div>
      </div>
    </>
  )
}

export function DetailDrawer({
  detail,
  onClose,
}: {
  detail: MapDetail | null
  onClose: () => void
}) {
  if (!detail) return null

  if (detail.type === 'vessel') {
    const v = VESSELS.find((x) => x.id === detail.id)
    if (!v) return null
    return (
      <DrawerShell
        icon={<Ship className="h-4.5 w-4.5" />}
        eyebrow={`Candidate · Rank ${v.rank}`}
        title={v.name}
        onClose={onClose}
      >
        <div className="mb-4 flex items-center gap-2">
          <StatusBadge tone={v.rank === 1 ? 'saffron' : 'navy'} dot={v.rank === 1}>
            {v.role}
          </StatusBadge>
          <span className="font-mono text-[11px] text-muted-foreground">{v.imo}</span>
        </div>

        <div className="mb-4 rounded-sm border border-border bg-muted/30 p-3">
          <div className="flex items-center justify-between">
            <span className="font-mono text-[10px] uppercase tracking-[0.1em] text-muted-foreground">
              Attribution Score
            </span>
            <span className="font-mono text-[16px] font-bold tabular-nums text-foreground">
              {v.attributionScore}%
            </span>
          </div>
          <Meter value={v.attributionScore} tone={v.rank === 1 ? 'saffron' : 'navy'} className="mt-2" />
        </div>

        <div className="grid grid-cols-2 gap-2">
          <Field label="Vessel Type" value={v.type} />
          <Field label="Flag" value={v.flag} />
          <Field label="Speed" value={`${v.speedKn} kn`} />
          <Field label="Heading" value={`${v.headingDeg}°`} />
          <Field label="Position" value={formatLat(v.position.lat)} />
          <Field label="" value={formatLng(v.position.lng)} />
          <Field label="Last AIS" value={v.lastSeenUtc} />
          <Field label="Track Points" value={`${v.track.length}`} />
        </div>

        <div className="mt-4">
          <div className="mb-1.5 font-mono text-[10px] uppercase tracking-[0.12em] text-muted-foreground">
            Analyst Notes
          </div>
          <p className="text-pretty rounded-sm border border-border bg-muted/30 p-3 text-[12px] leading-relaxed text-foreground/90">
            {v.notes}
          </p>
        </div>
      </DrawerShell>
    )
  }

  if (detail.type === 'slick') {
    return (
      <DrawerShell
        icon={<Droplets className="h-4.5 w-4.5" />}
        eyebrow="Detection"
        title="Slick Observation"
        onClose={onClose}
      >
        <div className="mb-4">
          <StatusBadge tone="ok" dot>
            SAR Confirmed
          </StatusBadge>
        </div>
        <div className="grid grid-cols-2 gap-2">
          <Field label="Area" value={SLICK_INFO.area} />
          <Field label="Distance from Coast" value={SLICK_INFO.distanceFromCoast} />
          <Field label="Observed" value={SLICK_INFO.observedUtc} />
          <Field label="Estimated Age" value={SLICK_INFO.estimatedAge} />
          <Field label="Confidence" value={SLICK_INFO.confidence} />
          <Field label="Center" value={formatLat(SLICK_INFO.center.lat)} />
        </div>
        <div className="mt-4">
          <div className="mb-1.5 font-mono text-[10px] uppercase tracking-[0.12em] text-muted-foreground">
            Sensor
          </div>
          <p className="rounded-sm border border-border bg-muted/30 p-3 text-[12px] leading-relaxed text-foreground/90">
            {SLICK_INFO.sensor}. Segmented footprint used as the terminal boundary condition for
            reverse-advection backtracking.
          </p>
        </div>
      </DrawerShell>
    )
  }

  // origin
  return (
    <DrawerShell
      icon={<Target className="h-4.5 w-4.5" />}
      eyebrow="Source Reconstruction"
      title="Most Likely Origin"
      onClose={onClose}
    >
      <div className="mb-4">
        <StatusBadge tone="saffron" dot>
          Peak {ORIGIN.peakLikelihood}%
        </StatusBadge>
      </div>
      <div className="grid grid-cols-2 gap-2">
        <Field label="Latitude" value={formatLat(ORIGIN.point.lat)} />
        <Field label="Longitude" value={formatLng(ORIGIN.point.lng)} />
        <Field label="Peak Likelihood" value={`${ORIGIN.peakLikelihood}%`} />
        <Field label="Search Radius" value={`${ORIGIN.radiusKm} km`} />
        <Field label="Estimated Release" value={ORIGIN.estimatedRelease} />
      </div>
      <div className="mt-4">
        <div className="mb-1.5 font-mono text-[10px] uppercase tracking-[0.12em] text-muted-foreground">
          Method
        </div>
        <p className="rounded-sm border border-border bg-muted/30 p-3 text-[12px] leading-relaxed text-foreground/90">
          {ORIGIN.method}. The likelihood field aggregates back-trajectory endpoints weighted by
          forcing-data confidence over the drift window.
        </p>
      </div>
    </DrawerShell>
  )
}
