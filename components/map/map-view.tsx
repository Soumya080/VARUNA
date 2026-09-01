'use client'

import {
  MAP_BOUNDS,
  ORIGIN,
  SLICK_INFO,
  VESSELS,
  formatLat,
  formatLng,
  project,
} from '@/lib/mock-data'
import { cn } from '@/lib/utils'
import { Crosshair, Navigation } from 'lucide-react'
import { useCallback, useRef, useState } from 'react'
import { MapControls } from './map-controls'
import type { LayerState, MapDetail } from './map-utils'
import { OriginProbability } from './origin-probability'
import { ParticleTrajectories } from './particle-trajectories'
import { SlickOverlay } from './slick-overlay'
import { VesselTracks } from './vessel-tracks'
import { WindVectors } from './wind-vectors'

const GRID_LATS = [16, 17, 18, 19, 20, 21]
const GRID_LNGS = [68, 69, 70, 71, 72, 73]

export function MapView({
  onSelectDetail,
  selectedVesselId,
}: {
  onSelectDetail: (d: MapDetail) => void
  selectedVesselId?: string
}) {
  const [layers, setLayers] = useState<LayerState>({
    slick: true,
    origin: true,
    particles: true,
    ais: true,
    wind: false,
  })
  const [zoom, setZoom] = useState(1)
  const [pan, setPan] = useState({ x: 0, y: 0 })
  const [hoverVessel, setHoverVessel] = useState<string | null>(null)
  const dragRef = useRef<{ x: number; y: number; px: number; py: number } | null>(null)

  const toggle = (k: keyof LayerState) => setLayers((s) => ({ ...s, [k]: !s[k] }))
  const zoomIn = () => setZoom((z) => Math.min(4, +(z + 0.4).toFixed(2)))
  const zoomOut = () =>
    setZoom((z) => {
      const nz = Math.max(1, +(z - 0.4).toFixed(2))
      if (nz === 1) setPan({ x: 0, y: 0 })
      return nz
    })
  const reset = () => {
    setZoom(1)
    setPan({ x: 0, y: 0 })
  }

  const onPointerDown = useCallback(
    (e: React.PointerEvent) => {
      if (zoom <= 1) return
      dragRef.current = { x: e.clientX, y: e.clientY, px: pan.x, py: pan.y }
      ;(e.currentTarget as HTMLElement).setPointerCapture(e.pointerId)
    },
    [zoom, pan],
  )
  const onPointerMove = useCallback((e: React.PointerEvent) => {
    if (!dragRef.current) return
    setPan({
      x: dragRef.current.px + (e.clientX - dragRef.current.x),
      y: dragRef.current.py + (e.clientY - dragRef.current.y),
    })
  }, [])
  const onPointerUp = () => {
    dragRef.current = null
  }

  const origin = project(ORIGIN.point)
  const slickCenter = project(SLICK_INFO.center)
  const markerScale = { transform: `scale(${1 / zoom})` }

  return (
    <section
      aria-label="Operational map"
      className="relative overflow-hidden rounded-sm border border-border bg-navy"
    >
      {/* Map header bar */}
      <div className="pointer-events-none absolute inset-x-0 top-0 z-20 flex items-start justify-between p-3">
        <div className="pointer-events-none rounded-sm" />
        <div className="pointer-events-none ml-auto rounded-sm border border-white/10 bg-navy/80 px-2.5 py-1 font-mono text-[10px] uppercase tracking-[0.12em] text-navy-foreground/70 backdrop-blur-sm">
          Arabian Sea · Indian EEZ
        </div>
      </div>

      <div
        className={cn(
          'relative aspect-[16/10] w-full touch-none select-none',
          zoom > 1 ? 'cursor-grab active:cursor-grabbing' : 'cursor-default',
        )}
        onPointerDown={onPointerDown}
        onPointerMove={onPointerMove}
        onPointerUp={onPointerUp}
        onPointerLeave={onPointerUp}
      >
        <div
          className="absolute inset-0 origin-center transition-transform duration-100"
          style={{ transform: `translate(${pan.x}px, ${pan.y}px) scale(${zoom})` }}
        >
          {/* Satellite basemap */}
          <img
            src="/maps/arabian-sea-satellite.png"
            alt="Satellite imagery of the Arabian Sea and western coast of India"
            className="absolute inset-0 h-full w-full object-cover"
            draggable={false}
          />
          {/* Tonal wash for readability */}
          <div
            className="absolute inset-0"
            style={{
              background:
                'radial-gradient(120% 90% at 30% 40%, transparent 40%, color-mix(in oklch, var(--navy) 55%, transparent) 100%)',
            }}
            aria-hidden="true"
          />

          {/* SVG overlays */}
          <svg
            className="absolute inset-0 h-full w-full"
            viewBox="0 0 100 100"
            preserveAspectRatio="none"
          >
            <defs>
              <radialGradient id="slickGradient" cx="50%" cy="50%" r="50%">
                <stop offset="0%" stopColor="var(--foreground)" stopOpacity="0.6" />
                <stop offset="55%" stopColor="var(--teal)" stopOpacity="0.28" />
                <stop offset="100%" stopColor="var(--teal)" stopOpacity="0" />
              </radialGradient>
              <radialGradient id="originGradient" cx="50%" cy="50%" r="50%">
                <stop offset="0%" stopColor="var(--saffron)" stopOpacity="0.55" />
                <stop offset="70%" stopColor="var(--saffron)" stopOpacity="0.14" />
                <stop offset="100%" stopColor="var(--saffron)" stopOpacity="0" />
              </radialGradient>
              <marker
                id="windArrow"
                markerWidth="4"
                markerHeight="4"
                refX="2"
                refY="2"
                orient="auto"
              >
                <path d="M0,0 L4,2 L0,4 Z" fill="var(--teal)" fillOpacity="0.7" />
              </marker>
            </defs>

            {/* Graticule */}
            <g aria-hidden="true">
              {GRID_LATS.map((lat) => {
                const y = project({ lat, lng: MAP_BOUNDS.lngMin }).y
                return (
                  <line
                    key={`lat-${lat}`}
                    x1={0}
                    y1={y}
                    x2={100}
                    y2={y}
                    stroke="var(--primary-foreground)"
                    strokeOpacity={0.1}
                    strokeWidth={0.5}
                    vectorEffect="non-scaling-stroke"
                  />
                )
              })}
              {GRID_LNGS.map((lng) => {
                const x = project({ lat: MAP_BOUNDS.latMin, lng }).x
                return (
                  <line
                    key={`lng-${lng}`}
                    x1={x}
                    y1={0}
                    x2={x}
                    y2={100}
                    stroke="var(--primary-foreground)"
                    strokeOpacity={0.1}
                    strokeWidth={0.5}
                    vectorEffect="non-scaling-stroke"
                  />
                )
              })}
            </g>

            {layers.wind && <WindVectors />}
            {layers.particles && <ParticleTrajectories />}
            {layers.ais && <VesselTracks selectedId={selectedVesselId} />}
            {layers.origin && (
              <OriginProbability onSelect={() => onSelectDetail({ type: 'origin' })} />
            )}
            {layers.slick && (
              <SlickOverlay onSelect={() => onSelectDetail({ type: 'slick' })} />
            )}
          </svg>

          {/* Graticule labels (HTML, crisp) */}
          <div className="pointer-events-none absolute inset-0" aria-hidden="true">
            {GRID_LATS.map((lat) => {
              const y = project({ lat, lng: MAP_BOUNDS.lngMin }).y
              return (
                <span
                  key={`llat-${lat}`}
                  className="absolute left-1 font-mono text-[8px] text-primary-foreground/40"
                  style={{ top: `${y}%`, transform: `translateY(-50%) scale(${1 / zoom})`, transformOrigin: 'left center' }}
                >
                  {lat}°N
                </span>
              )
            })}
            {GRID_LNGS.map((lng) => {
              const x = project({ lat: MAP_BOUNDS.latMin, lng }).x
              return (
                <span
                  key={`llng-${lng}`}
                  className="absolute bottom-1 font-mono text-[8px] text-primary-foreground/40"
                  style={{ left: `${x}%`, transform: `translateX(-50%) scale(${1 / zoom})`, transformOrigin: 'center bottom' }}
                >
                  {lng}°E
                </span>
              )
            })}
          </div>

          {/* Origin marker */}
          {layers.origin && (
            <button
              type="button"
              onClick={() => onSelectDetail({ type: 'origin' })}
              className="group absolute z-10 -translate-x-1/2 -translate-y-1/2"
              style={{ left: `${origin.x}%`, top: `${origin.y}%` }}
              aria-label="Most likely origin"
            >
              <span className="block" style={markerScale}>
                <span className="grid h-6 w-6 place-items-center rounded-full border border-saffron bg-navy/70 text-saffron shadow-[0_0_0_4px_color-mix(in_oklch,var(--saffron)_18%,transparent)]">
                  <Crosshair className="h-3.5 w-3.5" />
                </span>
                <span className="absolute left-1/2 top-full mt-1 w-max -translate-x-1/2 rounded-sm border border-saffron/40 bg-navy/85 px-1.5 py-0.5 text-center font-mono text-[8px] leading-tight text-saffron backdrop-blur-sm">
                  MOST LIKELY ORIGIN
                  <span className="block text-navy-foreground/70">
                    PEAK {ORIGIN.peakLikelihood}%
                  </span>
                </span>
              </span>
            </button>
          )}

          {/* Slick label */}
          {layers.slick && (
            <div
              className="pointer-events-none absolute z-10 -translate-x-1/2 -translate-y-1/2"
              style={{ left: `${slickCenter.x}%`, top: `${slickCenter.y}%` }}
            >
              <div
                className="rounded-sm border border-white/15 bg-navy/80 px-1.5 py-0.5 font-mono text-[8px] leading-tight text-navy-foreground backdrop-blur-sm"
                style={markerScale}
              >
                <div className="font-semibold text-primary-foreground">SLICK OBSERVATION</div>
                <div className="text-navy-foreground/70">
                  {SLICK_INFO.observedUtc} · {SLICK_INFO.area}
                </div>
              </div>
            </div>
          )}

          {/* Vessel markers */}
          {layers.ais &&
            VESSELS.map((v) => {
              const p = project(v.position)
              const isLead = v.rank === 1
              const selected = selectedVesselId === v.id
              return (
                <button
                  key={v.id}
                  type="button"
                  onClick={() => onSelectDetail({ type: 'vessel', id: v.id })}
                  onMouseEnter={() => setHoverVessel(v.id)}
                  onMouseLeave={() => setHoverVessel(null)}
                  className="absolute z-10 -translate-x-1/2 -translate-y-1/2"
                  style={{ left: `${p.x}%`, top: `${p.y}%` }}
                  aria-label={`Vessel ${v.name}`}
                >
                  <span className="relative block" style={markerScale}>
                    {(selected || isLead) && (
                      <span
                        className={cn(
                          'absolute left-1/2 top-1/2 h-7 w-7 -translate-x-1/2 -translate-y-1/2 rounded-full',
                          isLead ? 'bg-saffron/30' : 'bg-primary-foreground/25',
                          'animate-pulse-ring',
                        )}
                      />
                    )}
                    <span
                      className={cn(
                        'relative grid h-5 w-5 place-items-center rounded-full border shadow',
                        isLead
                          ? 'border-saffron bg-saffron text-saffron-foreground'
                          : 'border-white/40 bg-navy text-primary-foreground',
                        selected && 'ring-2 ring-white',
                      )}
                    >
                      <Navigation
                        className="h-2.5 w-2.5"
                        style={{ transform: `rotate(${v.headingDeg}deg)` }}
                        fill="currentColor"
                      />
                    </span>

                    {hoverVessel === v.id && (
                      <span className="absolute bottom-full left-1/2 z-30 mb-1.5 w-44 -translate-x-1/2 rounded-sm border border-white/15 bg-navy/90 p-2 text-left backdrop-blur-sm">
                        <span className="flex items-center justify-between gap-2">
                          <span className="font-mono text-[10px] font-semibold text-primary-foreground">
                            {v.name}
                          </span>
                          <span className="font-mono text-[9px] font-semibold text-saffron">
                            {v.attributionScore}%
                          </span>
                        </span>
                        <span className="mt-0.5 block font-mono text-[9px] text-navy-foreground/60">
                          {v.type} · {v.flag}
                        </span>
                        <span className="mt-1 block font-mono text-[9px] text-navy-foreground/50">
                          {v.speedKn} kn · {v.headingDeg}° · {v.lastSeenUtc}
                        </span>
                      </span>
                    )}
                  </span>
                </button>
              )
            })}
        </div>

        <MapControls
          layers={layers}
          onToggle={toggle}
          onZoomIn={zoomIn}
          onZoomOut={zoomOut}
          onReset={reset}
        />
      </div>

      {/* Footer readout */}
      <div className="flex flex-wrap items-center justify-between gap-2 border-t border-white/10 bg-navy px-3 py-1.5">
        <span className="font-mono text-[9px] uppercase tracking-[0.12em] text-navy-foreground/50">
          SAR · Sentinel-1 · 12 JUN 06:42 UTC
        </span>
        <span className="font-mono text-[9px] tabular-nums text-navy-foreground/60">
          ORIGIN {formatLat(ORIGIN.point.lat)} {formatLng(ORIGIN.point.lng)} · ZOOM {zoom.toFixed(1)}×
        </span>
      </div>
    </section>
  )
}
