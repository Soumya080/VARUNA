import { project, type GeoPoint } from '@/lib/mock-data'

/** Build an SVG path string (in 0–100 overlay space) from geo points. */
export function toPath(points: GeoPoint[], close = false): string {
  const d = points
    .map((p, i) => {
      const { x, y } = project(p)
      return `${i === 0 ? 'M' : 'L'} ${x.toFixed(2)} ${y.toFixed(2)}`
    })
    .join(' ')
  return close ? `${d} Z` : d
}

export type MapDetail =
  | { type: 'vessel'; id: string }
  | { type: 'slick' }
  | { type: 'origin' }

export interface LayerState {
  slick: boolean
  origin: boolean
  particles: boolean
  ais: boolean
  wind: boolean
}
