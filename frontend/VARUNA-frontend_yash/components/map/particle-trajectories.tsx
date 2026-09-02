'use client'

import { PARTICLE_TRAJECTORIES } from '@/lib/mock-data'
import { toPath } from './map-utils'

export function ParticleTrajectories() {
  return (
    <g aria-hidden="true">
      {PARTICLE_TRAJECTORIES.map((traj, i) => {
        const d = toPath(traj)
        return (
          <g key={i}>
            {/* Base faint line */}
            <path
              d={d}
              fill="none"
              stroke="var(--teal)"
              strokeOpacity={0.45}
              strokeWidth={0.9}
              vectorEffect="non-scaling-stroke"
            />
            {/* Animated flow overlay */}
            <path
              d={d}
              fill="none"
              stroke="var(--teal)"
              strokeOpacity={0.95}
              strokeWidth={1.1}
              strokeDasharray="4 10"
              vectorEffect="non-scaling-stroke"
              className="animate-dash-flow"
              style={{ animationDelay: `${i * 0.6}s` }}
            />
          </g>
        )
      })}
    </g>
  )
}
