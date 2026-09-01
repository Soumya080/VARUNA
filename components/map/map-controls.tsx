'use client'

import { cn } from '@/lib/utils'
import { Layers, Maximize2, Minus, Plus } from 'lucide-react'
import { useState } from 'react'
import type { LayerState } from './map-utils'

const LAYER_META: { key: keyof LayerState; label: string; swatch: string }[] = [
  { key: 'slick', label: 'Slick', swatch: 'var(--foreground)' },
  { key: 'origin', label: 'Origin Probability', swatch: 'var(--saffron)' },
  { key: 'particles', label: 'Particle Paths', swatch: 'var(--teal)' },
  { key: 'ais', label: 'AIS Tracks', swatch: 'var(--primary-foreground)' },
  { key: 'wind', label: 'Wind Vectors', swatch: 'var(--teal)' },
]

export function MapControls({
  layers,
  onToggle,
  onZoomIn,
  onZoomOut,
  onReset,
}: {
  layers: LayerState
  onToggle: (k: keyof LayerState) => void
  onZoomIn: () => void
  onZoomOut: () => void
  onReset: () => void
}) {
  const [panelOpen, setPanelOpen] = useState(true)

  return (
    <>
      {/* Layer panel — top left */}
      <div className="absolute left-3 top-3 z-10 w-44">
        <button
          type="button"
          onClick={() => setPanelOpen((o) => !o)}
          className="flex w-full items-center gap-2 rounded-sm border border-white/10 bg-navy/85 px-2.5 py-1.5 font-mono text-[10px] font-semibold uppercase tracking-[0.12em] text-navy-foreground backdrop-blur-sm"
          aria-expanded={panelOpen}
        >
          <Layers className="h-3.5 w-3.5 text-saffron" />
          Layers
        </button>
        {panelOpen && (
          <div className="mt-1 space-y-0.5 rounded-sm border border-white/10 bg-navy/85 p-1.5 backdrop-blur-sm">
            {LAYER_META.map((l) => {
              const on = layers[l.key]
              return (
                <button
                  key={l.key}
                  type="button"
                  onClick={() => onToggle(l.key)}
                  className={cn(
                    'flex w-full items-center gap-2 rounded-sm px-1.5 py-1 text-left text-[11px] transition-colors',
                    on
                      ? 'text-navy-foreground hover:bg-white/5'
                      : 'text-navy-foreground/40 hover:bg-white/5',
                  )}
                  aria-pressed={on}
                >
                  <span
                    className="h-2.5 w-2.5 shrink-0 rounded-[2px] border"
                    style={{
                      backgroundColor: on ? l.swatch : 'transparent',
                      borderColor: l.swatch,
                    }}
                  />
                  {l.label}
                  <span
                    className={cn(
                      'ml-auto h-1.5 w-1.5 rounded-full',
                      on ? 'bg-saffron' : 'bg-white/15',
                    )}
                  />
                </button>
              )
            })}
          </div>
        )}
      </div>

      {/* Zoom controls — bottom right */}
      <div className="absolute bottom-3 right-3 z-10 flex flex-col overflow-hidden rounded-sm border border-white/10 bg-navy/85 backdrop-blur-sm">
        {[
          { icon: Plus, fn: onZoomIn, label: 'Zoom in' },
          { icon: Minus, fn: onZoomOut, label: 'Zoom out' },
          { icon: Maximize2, fn: onReset, label: 'Reset view' },
        ].map(({ icon: Icon, fn, label }, i) => (
          <button
            key={label}
            type="button"
            onClick={fn}
            aria-label={label}
            className={cn(
              'grid h-8 w-8 place-items-center text-navy-foreground/80 transition-colors hover:bg-white/10 hover:text-navy-foreground',
              i > 0 && 'border-t border-white/10',
            )}
          >
            <Icon className="h-3.5 w-3.5" />
          </button>
        ))}
      </div>
    </>
  )
}
