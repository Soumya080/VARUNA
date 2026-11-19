'use client'

import { SLICK_POLYGON } from '@/lib/mock-data'
import { toPath } from './map-utils'

export function SlickOverlay({ onSelect }: { onSelect?: () => void }) {
  const d = toPath(SLICK_POLYGON, true)
  return (
    <g
      className="cursor-pointer"
      onClick={(e) => {
        e.stopPropagation()
        onSelect?.()
      }}
      role="button"
      aria-label="Oil slick observation"
    >
      {/* Soft halo */}
      <path d={d} fill="url(#slickGradient)" opacity={0.9} />
      {/* Crisp outline */}
      <path
        d={d}
        fill="none"
        stroke="var(--foreground)"
        strokeOpacity={0.55}
        strokeWidth={1}
        strokeDasharray="2 1.5"
        vectorEffect="non-scaling-stroke"
      />
      <path
        d={d}
        fill="transparent"
        className="transition-[fill] hover:fill-[color-mix(in_oklch,var(--foreground)_10%,transparent)]"
      />
    </g>
  )
}
