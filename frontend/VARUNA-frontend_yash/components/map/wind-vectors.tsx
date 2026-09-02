'use client'

/**
 * Decorative wind-forcing field. In production this would render actual
 * gridded wind/current vectors (e.g. from GFS/HYCOM) supplied by the backend.
 */
export function WindVectors() {
  const cols = 9
  const rows = 6
  const cells: { x: number; y: number }[] = []
  for (let r = 0; r < rows; r++) {
    for (let c = 0; c < cols; c++) {
      cells.push({
        x: (c + 0.5) * (100 / cols),
        y: (r + 0.5) * (100 / rows),
      })
    }
  }
  // Gentle south-westerly flow with mild spatial variation.
  return (
    <g aria-hidden="true" opacity={0.5}>
      {cells.map((cell, i) => {
        const angle = 205 + Math.sin(cell.x / 18 + cell.y / 12) * 14
        const rad = (angle * Math.PI) / 180
        const len = 2.6
        const x2 = cell.x + Math.cos(rad) * len
        const y2 = cell.y + Math.sin(rad) * len
        return (
          <line
            key={i}
            x1={cell.x}
            y1={cell.y}
            x2={x2}
            y2={y2}
            stroke="var(--teal)"
            strokeOpacity={0.7}
            strokeWidth={0.7}
            markerEnd="url(#windArrow)"
            vectorEffect="non-scaling-stroke"
          />
        )
      })}
    </g>
  )
}
