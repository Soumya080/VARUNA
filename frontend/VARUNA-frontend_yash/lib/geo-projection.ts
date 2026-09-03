/**
 * Shared lon/lat -> unit-square projection math (Phase 1).
 *
 * Extracted out of `lib/mock-data.ts` so real-data panels (CHHAYA's tile
 * mini-map) can use the exact same, already-tested math without importing
 * from `mock-data.ts` — `components/cockpit/*` deliberately imports nothing
 * from it (see that file's own header comment). This module has no mock
 * data in it at all, just the projection.
 *
 * Equirectangular (plate carrée), not a real map projection — adequate for
 * a small bbox (a SAR tile, a case's immediate surroundings), consistent
 * with `varuna_geospatial`'s existing flat-earth approximations on the
 * backend. Never presented as navigation-grade.
 */

export interface LonLatBBox {
  min_lon: number
  min_lat: number
  max_lon: number
  max_lat: number
}

export interface UnitPoint {
  x: number
  y: number
}

/**
 * Project a (lon, lat) point into 0-100 overlay percentage space for the
 * given bbox. y=0 is the NORTH edge (max_lat), matching standard raster/
 * screen convention (row 0 = top).
 */
export function projectToBBox(
  lon: number,
  lat: number,
  bbox: LonLatBBox,
): UnitPoint {
  const lonSpan = bbox.max_lon - bbox.min_lon || 1e-9
  const latSpan = bbox.max_lat - bbox.min_lat || 1e-9
  const x = ((lon - bbox.min_lon) / lonSpan) * 100
  const y = ((bbox.max_lat - lat) / latSpan) * 100
  return { x, y }
}

/** Whether a projected point actually falls inside the 0-100 frame (with a
 * small tolerance) — used to distinguish "off the edge of this tile" from a
 * genuinely invalid coordinate, which callers already track separately. */
export function isWithinFrame(p: UnitPoint, toleranceUnits = 5): boolean {
  return (
    p.x >= -toleranceUnits && p.x <= 100 + toleranceUnits &&
    p.y >= -toleranceUnits && p.y <= 100 + toleranceUnits
  )
}
