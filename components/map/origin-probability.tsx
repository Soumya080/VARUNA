'use client'

import { ORIGIN, project } from '@/lib/mock-data'

export function OriginProbability({ onSelect }: { onSelect?: () => void }) {
  const { x, y } = project(ORIGIN.point)
  // Approx overlay radius from km (rough visual scale for the placeholder map).
  const r = 10

  return (
    <g
      className="cursor-pointer"
      onClick={(e) => {
        e.stopPropagation()
        onSelect?.()
      }}
      role="button"
      aria-label="Reconstructed source probability field"
    >
      {[r, r * 0.68, r * 0.38].map((radius, i) => (
        <circle
          key={i}
          cx={x}
          cy={y}
          r={radius}
          fill="url(#originGradient)"
          opacity={0.55}
        />
      ))}
      {/* Contour rings */}
      {[r, r * 0.68, r * 0.38].map((radius, i) => (
        <circle
          key={`c-${i}`}
          cx={x}
          cy={y}
          r={radius}
          fill="none"
          stroke="var(--saffron)"
          strokeOpacity={0.5}
          strokeWidth={0.8}
          strokeDasharray="1.5 1.5"
          vectorEffect="non-scaling-stroke"
        />
      ))}
    </g>
  )
}
