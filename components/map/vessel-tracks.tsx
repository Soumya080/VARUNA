'use client'

import { VESSELS } from '@/lib/mock-data'
import { toPath } from './map-utils'

export function VesselTracks({ selectedId }: { selectedId?: string }) {
  return (
    <g aria-hidden="true">
      {VESSELS.map((v) => {
        const d = toPath(v.track)
        const active = selectedId === v.id
        const isLead = v.rank === 1
        return (
          <path
            key={v.id}
            d={d}
            fill="none"
            stroke={isLead ? 'var(--saffron)' : 'var(--primary-foreground)'}
            strokeOpacity={active ? 1 : isLead ? 0.85 : 0.5}
            strokeWidth={active ? 1.6 : 1.1}
            strokeDasharray="0.5 2.5"
            strokeLinecap="round"
            vectorEffect="non-scaling-stroke"
          />
        )
      })}
    </g>
  )
}
