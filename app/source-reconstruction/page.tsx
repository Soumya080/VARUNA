'use client'

import { ORIGIN, PARTICLE_TRAJECTORIES } from '@/lib/mock-data'
import { SectionLabel, StatusBadge, Meter } from '@/components/primitives'
import { Waypoints, Wind, Droplets, Compass, Target, Timer, MapPin, ArrowDownRight } from 'lucide-react'

const FORCING_DATA = [
  { label: 'Ocean Current Model', value: 'HYCOM (Global 1/12°)', status: 'ok', coverage: 100 },
  { label: 'Wind Forcing', value: 'GFS (0.25° resolution)', status: 'ok', coverage: 100 },
  { label: 'Wave Model', value: 'WAVEWATCH III', status: 'ok', coverage: 98 },
  { label: 'Tidal Harmonics', value: 'FES2014 (32 constituents)', status: 'ok', coverage: 100 },
  { label: 'SST Analysis', value: 'OSTIA L4', status: 'ok', coverage: 95 },
]

const DRIFT_PARAMETERS = [
  { icon: Timer, label: 'Drift Window', value: '38.5 hours' },
  { icon: Waypoints, label: 'Ensemble Size', value: '4,000 particles' },
  { icon: ArrowDownRight, label: 'Method', value: 'Adjoint back-trajectory' },
  { icon: Wind, label: 'Wind Drift Factor', value: '3.5%' },
  { icon: Compass, label: 'Stokes Drift', value: 'Included' },
  { icon: Droplets, label: 'Diffusion', value: 'Random walk (K = 10 m²/s)' },
]

const UNCERTAINTY = [
  { label: 'Current velocity', value: '± 0.05 m/s', impact: 'Moderate' },
  { label: 'Wind speed', value: '± 1.2 m/s', impact: 'Low' },
  { label: 'Release timing', value: '± 2 hours', impact: 'High' },
  { label: 'Weathering rate', value: '± 15%', impact: 'Low' },
  { label: 'Initial slick shape', value: '± 20% area', impact: 'Low' },
]

export default function SourceReconstructionPage() {
  return (
    <>
      <div className="mb-3 flex flex-wrap items-end justify-between gap-2">
        <div>
          <h1 className="text-balance text-lg font-semibold leading-tight tracking-tight text-foreground sm:text-xl">
            Source Reconstruction
          </h1>
          <p className="mt-0.5 font-mono text-[11px] uppercase tracking-[0.1em] text-muted-foreground">
            Case 24-071 · Reverse Advection & Origin Field · Stages 02–03
          </p>
        </div>
        <StatusBadge tone="ok" dot>Completed</StatusBadge>
      </div>

      {/* Origin estimate card */}
      <section className="rounded-sm border border-saffron/30 bg-saffron/5 p-4">
        <div className="flex items-center gap-2 mb-3">
          <Target className="h-4 w-4 text-saffron" />
          <SectionLabel className="text-saffron">Reconstructed Origin</SectionLabel>
        </div>
        <div className="grid grid-cols-2 gap-3 sm:grid-cols-4 lg:grid-cols-6">
          <div className="rounded-sm border border-saffron/20 bg-card p-3">
            <div className="font-mono text-[9px] uppercase tracking-[0.1em] text-muted-foreground mb-1">Latitude</div>
            <div className="font-mono text-[15px] font-bold text-foreground">{ORIGIN.point.lat.toFixed(3)}° N</div>
          </div>
          <div className="rounded-sm border border-saffron/20 bg-card p-3">
            <div className="font-mono text-[9px] uppercase tracking-[0.1em] text-muted-foreground mb-1">Longitude</div>
            <div className="font-mono text-[15px] font-bold text-foreground">{ORIGIN.point.lng.toFixed(3)}° E</div>
          </div>
          <div className="rounded-sm border border-saffron/20 bg-card p-3">
            <div className="font-mono text-[9px] uppercase tracking-[0.1em] text-muted-foreground mb-1">Peak Likelihood</div>
            <div className="font-mono text-[15px] font-bold text-saffron">{ORIGIN.peakLikelihood}%</div>
          </div>
          <div className="rounded-sm border border-saffron/20 bg-card p-3">
            <div className="font-mono text-[9px] uppercase tracking-[0.1em] text-muted-foreground mb-1">Est. Release</div>
            <div className="font-mono text-[13px] font-bold text-foreground">16:30 UTC ± 2 h</div>
          </div>
          <div className="rounded-sm border border-saffron/20 bg-card p-3">
            <div className="font-mono text-[9px] uppercase tracking-[0.1em] text-muted-foreground mb-1">Radius (95%)</div>
            <div className="font-mono text-[15px] font-bold text-foreground">{ORIGIN.radiusKm} km</div>
          </div>
          <div className="rounded-sm border border-saffron/20 bg-card p-3">
            <div className="font-mono text-[9px] uppercase tracking-[0.1em] text-muted-foreground mb-1">Trajectories</div>
            <div className="font-mono text-[15px] font-bold text-foreground">{PARTICLE_TRAJECTORIES.length}</div>
          </div>
        </div>
      </section>

      {/* Drift parameters + Forcing data */}
      <div className="mt-3 grid grid-cols-1 gap-3 lg:grid-cols-2">
        <section className="rounded-sm border border-border bg-card p-4">
          <div className="mb-3 flex items-center gap-2">
            <Waypoints className="h-4 w-4 text-teal" />
            <SectionLabel>Drift Model Parameters</SectionLabel>
          </div>
          <div className="grid grid-cols-1 gap-2 sm:grid-cols-2">
            {DRIFT_PARAMETERS.map((item) => (
              <div key={item.label} className="flex items-start gap-2.5 rounded-sm border border-border bg-background/50 p-2.5">
                <item.icon className="h-4 w-4 shrink-0 text-teal mt-0.5" />
                <div>
                  <div className="font-mono text-[9px] uppercase tracking-[0.1em] text-muted-foreground">{item.label}</div>
                  <div className="mt-0.5 text-[12px] font-medium text-foreground">{item.value}</div>
                </div>
              </div>
            ))}
          </div>
        </section>

        <section className="rounded-sm border border-border bg-card p-4">
          <div className="mb-3 flex items-center gap-2">
            <Wind className="h-4 w-4 text-saffron" />
            <SectionLabel>Environmental Forcing Data</SectionLabel>
          </div>
          <div className="space-y-3">
            {FORCING_DATA.map((item) => (
              <div key={item.label}>
                <div className="flex items-center justify-between mb-1">
                  <span className="text-[12px] text-muted-foreground">{item.label}</span>
                  <div className="flex items-center gap-2">
                    <span className="font-mono text-[11px] font-medium text-foreground">{item.value}</span>
                    <span className="h-1.5 w-1.5 rounded-full bg-[var(--ok)]" />
                  </div>
                </div>
                <Meter value={item.coverage} tone="teal" />
              </div>
            ))}
          </div>
        </section>
      </div>

      {/* Uncertainty analysis */}
      <section className="mt-3 rounded-sm border border-border bg-card p-4">
        <SectionLabel>Uncertainty Analysis</SectionLabel>
        <div className="mt-3 overflow-x-auto">
          <table className="w-full text-left">
            <thead>
              <tr className="border-b border-border">
                <th className="pb-2 font-mono text-[9px] font-semibold uppercase tracking-[0.12em] text-muted-foreground">Source</th>
                <th className="pb-2 font-mono text-[9px] font-semibold uppercase tracking-[0.12em] text-muted-foreground">Uncertainty</th>
                <th className="pb-2 font-mono text-[9px] font-semibold uppercase tracking-[0.12em] text-muted-foreground">Impact</th>
              </tr>
            </thead>
            <tbody>
              {UNCERTAINTY.map((item) => (
                <tr key={item.label} className="border-b border-border/50 last:border-b-0">
                  <td className="py-2 text-[12px] text-foreground">{item.label}</td>
                  <td className="py-2 font-mono text-[12px] font-medium text-foreground">{item.value}</td>
                  <td className="py-2">
                    <StatusBadge tone={item.impact === 'High' ? 'warn' : item.impact === 'Moderate' ? 'saffron' : 'ok'}>
                      {item.impact}
                    </StatusBadge>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </section>

      {/* Method description */}
      <section className="mt-3 rounded-sm border border-border bg-card p-4">
        <SectionLabel>Methodology</SectionLabel>
        <p className="mt-2 text-[12px] leading-relaxed text-muted-foreground">
          {ORIGIN.method}. Particles are released from the observed slick footprint and advected backward through time using
          a 4th-order Runge-Kutta integration scheme with a 15-minute time step. Wind drift at 3.5% of 10 m wind speed is
          applied with a 15° deflection angle. Random walk diffusion (K = 10 m²/s) accounts for sub-grid turbulence. The
          resulting back-trajectory density is kernel-smoothed onto a 500 m grid to produce the spatial likelihood field for
          the release location.
        </p>
      </section>
    </>
  )
}
