'use client'

/**
 * VARUNA Mission Cockpit — real dynamic map.
 *
 * Replaces the static Arabian-Sea image + hardcoded MAP_BOUNDS the legacy
 * map used. Every coordinate here originates from the canonical
 * OperatorCase; there is not one hardcoded lat/lon, centre or zoom in this
 * file. The viewport is derived with `fitBounds()` over whatever real
 * geometry the case actually carries, so CASE-VALID opens over the Gulf of
 * Mexico purely because that is where its detection centroid is.
 *
 * Layers are rendered ONLY when the backend actually produced them. A
 * missing trajectory is reported as missing (see `TRAJECTORY NOTE` below)
 * rather than drawn from invented coordinates.
 */
import { useEffect, useMemo } from 'react'
import {
  CircleMarker,
  LayersControl,
  MapContainer,
  Polyline,
  Popup,
  Rectangle,
  ScaleControl,
  TileLayer,
  Tooltip,
  useMap,
} from 'react-leaflet'
import type { LatLngBoundsExpression, LatLngExpression } from 'leaflet'
import 'leaflet/dist/leaflet.css'
import type { BBoxValue, OperatorCase, PhiFieldValue, BackdriftPathPoint } from '@/lib/operator-case-types'

function bboxToBounds(b: BBoxValue): LatLngBoundsExpression {
  return [
    [b.min_lat, b.min_lon],
    [b.max_lat, b.max_lon],
  ]
}

/** Imperatively fit the viewport to the case's real geometry. */
function FitToCase({ bounds }: { bounds: LatLngBoundsExpression | null }) {
  const map = useMap()
  useEffect(() => {
    if (bounds) map.fitBounds(bounds, { padding: [48, 48], maxZoom: 11 })
  }, [bounds, map])
  return null
}

export interface CaseMapProps {
  operatorCase: OperatorCase
}

export function CaseMap({ operatorCase: oc }: CaseMapProps) {
  const sp = oc.starting_point
  const startPoint =
    sp?.status === 'STARTING_POINT_AVAILABLE' && sp.point
      ? ([sp.point.lat, sp.point.lon] as LatLngExpression)
      : null

  const detection = oc.detection.status === 'produced' ? oc.detection.value : null
  const detectionBbox = detection?.bbox ?? null
  const detectionCentroid = detection?.centroid ?? null

  const originValue: PhiFieldValue | null =
    oc.origin.status === 'produced' ? oc.origin.value : null
  const phiBbox: BBoxValue | null = originValue?.bbox ?? null

  // ADR-0017: backward-drift centroid path derived from the real Phi histogram.
  const backdriftPath: BackdriftPathPoint[] = originValue?.backdrift_path ?? []
  const isMultimodal: boolean = originValue?.diagnostics?.multimodal ?? false

  const forecast = oc.forecast.status === 'produced' ? oc.forecast.value : null
  const landfalls = forecast?.landfalls ?? []

  const aisTracks = oc.ais.status === 'produced' ? (oc.ais.value ?? []) : []

  // Phase 9 (docs/product/HONESTY_LEDGER.md #27): `MissionRecord.tasking`
  // — real bbox/center/area/pattern/PoD/rationale, computed since ADR-0015
  // and stored, but never drawn. One search box per real mission that
  // actually carries one.
  const missionSearchBoxes =
    oc.mission.status === 'produced'
      ? (oc.mission.value ?? []).filter((m) => m.tasking?.search_box)
      : []

  // Collect every real coordinate the case carries, then fit to their union.
  const bounds = useMemo<LatLngBoundsExpression | null>(() => {
    const pts: [number, number][] = []
    if (startPoint) pts.push(startPoint as [number, number])
    if (detectionCentroid) pts.push([detectionCentroid.lat, detectionCentroid.lon])
    const boxes: (BBoxValue | null)[] = [
      detectionBbox,
      phiBbox,
      ...missionSearchBoxes.map((m) => m.tasking!.search_box.bbox),
    ]
    for (const b of boxes) {
      if (b) {
        pts.push([b.min_lat, b.min_lon])
        pts.push([b.max_lat, b.max_lon])
      }
    }
    for (const lf of landfalls) {
      if (lf.position) pts.push([lf.position.lat, lf.position.lon])
    }
    for (const bp of backdriftPath) {
      pts.push([bp.lat, bp.lon])
    }
    if (pts.length === 0) return null
    const lats = pts.map((p) => p[0])
    const lons = pts.map((p) => p[1])
    // A single point yields a degenerate bbox; pad it so fitBounds has extent.
    const pad = 0.05
    return [
      [Math.min(...lats) - pad, Math.min(...lons) - pad],
      [Math.max(...lats) + pad, Math.max(...lons) + pad],
    ]
  }, [startPoint, detectionCentroid, detectionBbox, phiBbox, landfalls, missionSearchBoxes, backdriftPath])

  // TRAJECTORY NOTE: ForwardForecast carries `trajectory_path` (a .npz
  // reference), not a coordinate array, and PhiField carries a bbox +
  // spatial_modes rather than a polyline. When the contract does supply
  // real vertices we draw them; we never synthesise a curve to make the
  // map look richer.
  const forwardTrack: LatLngExpression[] =
    startPoint && landfalls.length > 0 && landfalls[0].position
      ? [startPoint, [landfalls[0].position.lat, landfalls[0].position.lon]]
      : []
  const forwardTrackIsRealPolyline = false // see TRAJECTORY NOTE

  if (!bounds) {
    return (
      <div className="grid h-full min-h-[420px] place-items-center rounded-sm border border-border bg-card px-6 text-center">
        <div>
          <div className="font-mono text-[11px] font-semibold uppercase tracking-[0.12em] text-[var(--warn)]">
            No geographic evidence for this case
          </div>
          <p className="mt-1.5 max-w-md text-[12px] leading-snug text-muted-foreground">
            {sp?.reason ??
              'The backend produced no detection geometry, origin bbox or forecast position, so there is nothing to place on a map. No default location is substituted.'}
          </p>
        </div>
      </div>
    )
  }

  return (
    <MapContainer
      bounds={bounds}
      scrollWheelZoom
      className="h-full min-h-[420px] w-full rounded-sm"
      style={{ background: 'var(--navy)' }}
    >
      <FitToCase bounds={bounds} />
      <ScaleControl position="bottomleft" imperial={false} />

      <LayersControl position="topright">
        <LayersControl.BaseLayer checked name="Satellite (Esri World Imagery)">
          <TileLayer
            attribution="Imagery &copy; Esri, Maxar, Earthstar Geographics"
            url="https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{z}/{y}/{x}"
            maxZoom={18}
          />
        </LayersControl.BaseLayer>
        <LayersControl.BaseLayer name="Ocean basemap (Esri)">
          <TileLayer
            attribution="Esri, GEBCO, NOAA, National Geographic"
            url="https://server.arcgisonline.com/ArcGIS/rest/services/Ocean/World_Ocean_Base/MapServer/tile/{z}/{y}/{x}"
            maxZoom={13}
          />
        </LayersControl.BaseLayer>
        <LayersControl.BaseLayer name="Street (OpenStreetMap)">
          <TileLayer
            attribution='&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a> contributors'
            url="https://tile.openstreetmap.org/{z}/{x}/{y}.png"
          />
        </LayersControl.BaseLayer>

        <LayersControl.Overlay checked name="Place labels">
          <TileLayer
            attribution="Esri"
            url="https://server.arcgisonline.com/ArcGIS/rest/services/Reference/World_Boundaries_and_Places/MapServer/tile/{z}/{y}/{x}"
          />
        </LayersControl.Overlay>
        <LayersControl.Overlay name="Marine / seamarks (OpenSeaMap)">
          <TileLayer
            attribution="&copy; OpenSeaMap contributors"
            url="https://tiles.openseamap.org/seamark/{z}/{x}/{y}.png"
          />
        </LayersControl.Overlay>
      </LayersControl>

      {/* SAR / detection footprint */}
      {detectionBbox && (
        <Rectangle
          bounds={bboxToBounds(detectionBbox)}
          pathOptions={{ color: '#e8871a', weight: 2, fillOpacity: 0.14 }}
        >
          <Popup>
            <strong>NETRA detection footprint</strong>
            <br />
            {detection?.classification ?? 'unclassified'} · confidence{' '}
            {detection?.confidence ?? '—'}
            <br />
            area {detection?.area_km2 ?? '—'} km²
          </Popup>
          <Tooltip permanent direction="top">
            <span style={{ fontSize: 10 }}>NETRA slick footprint</span>
          </Tooltip>
        </Rectangle>
      )}

      {/* PRATIVARTAN backward-reconstruction support (Phi bbox) */}
      {phiBbox && (
        <Rectangle
          bounds={bboxToBounds(phiBbox)}
          pathOptions={{ color: '#3b82f6', weight: 1, dashArray: '5 4', fillOpacity: 0.06 }}
        >
          <Popup>
            <strong>PRATIVARTAN Φ support</strong>
            <br />
            Backward-reconstruction probability field extent.
          </Popup>
        </Rectangle>
      )}

      {/* ADR-0017: PRATIVARTAN backward-drift centroid path — the probability-
          mass-weighted centroid of each Phi time slice, drawn oldest-first
          (origin → observation). NOT a single particle's trajectory — this is
          a summary statistic of a probability distribution. When the field is
          multimodal, the centroid can be misleading (it averages competing
          lobes); the popup warns about this. */}
      {backdriftPath.length >= 2 && (
        <Polyline
          positions={backdriftPath.map((p) => [p.lat, p.lon] as LatLngExpression)}
          pathOptions={{
            color: isMultimodal ? '#f59e0b' : '#8b5cf6',
            weight: 3,
            opacity: 0.85,
            dashArray: isMultimodal ? '6 4' : undefined,
          }}
        >
          <Popup>
            <strong>PRATIVARTAN backward-drift path</strong>
            <br />
            {backdriftPath.length} time slices &middot; oldest: {backdriftPath[0]?.time_hours.toFixed(1)}h ago
            <br />
            <em>
              Probability-mass centroid of the &Phi; histogram per time bin
              &mdash; NOT a single particle&apos;s trajectory.
            </em>
            {isMultimodal && (
              <>
                <br />
                <span style={{ color: '#f59e0b', fontWeight: 600 }}>
                  ⚠ Field is multimodal — competing origin hypotheses exist.
                  This centroid averages them; individual lobes may be far apart.
                </span>
              </>
            )}
          </Popup>
          <Tooltip permanent={false}>
            <span style={{ fontSize: 10 }}>BACKWARD DRIFT PATH</span>
          </Tooltip>
        </Polyline>
      )}
      {/* Origin endpoint marker — the oldest point on the backdrift path */}
      {backdriftPath.length > 0 && (
        <CircleMarker
          center={[backdriftPath[0].lat, backdriftPath[0].lon]}
          radius={7}
          pathOptions={{ color: '#fff', weight: 2, fillColor: '#8b5cf6', fillOpacity: 0.9 }}
        >
          <Popup>
            <strong>Estimated origin area</strong>
            <br />
            {backdriftPath[0].time_hours.toFixed(1)}h before observation
            <br />
            {Math.abs(backdriftPath[0].lat).toFixed(4)}&deg;{backdriftPath[0].lat >= 0 ? 'N' : 'S'}{' '}
            {Math.abs(backdriftPath[0].lon).toFixed(4)}&deg;{backdriftPath[0].lon >= 0 ? 'E' : 'W'}
            <br />
            mass: {(backdriftPath[0].mass_fraction * 100).toFixed(1)}% of &Phi;
          </Popup>
          <Tooltip permanent direction="left" offset={[-10, 0]}>
            <span style={{ fontSize: 10, fontWeight: 600 }}>ORIGIN ({backdriftPath[0].time_hours.toFixed(0)}h)</span>
          </Tooltip>
        </CircleMarker>
      )}

      {/* Mission search box(es) — MissionRecord.tasking.search_box, real
          bbox/pattern/PoD, computed since ADR-0015 and previously never
          drawn (Phase 9 fix, docs/product/HONESTY_LEDGER.md #27). */}
      {missionSearchBoxes.map((m) => (
        <Rectangle
          key={m.mission_id}
          bounds={bboxToBounds(m.tasking!.search_box.bbox)}
          pathOptions={{ color: '#22c55e', weight: 2, dashArray: '3 3', fillOpacity: 0.08 }}
        >
          <Popup>
            <strong>Mission search box — {m.mission_id}</strong>
            <br />
            Pattern: {m.tasking!.pattern.replace(/_/g, ' ')}
            <br />
            Asset: {m.tasking!.base_name} ({m.tasking!.asset_type})
            <br />
            PoD: {(m.tasking!.probability_of_detection * 100).toFixed(0)}%
            <br />
            {m.tasking!.rationale}
          </Popup>
          <Tooltip permanent direction="bottom">
            <span style={{ fontSize: 10 }}>MISSION SEARCH BOX</span>
          </Tooltip>
        </Rectangle>
      ))}

      {/* PRAVAAH forward reach — straight segment ONLY, explicitly not a
          modelled drift path (see TRAJECTORY NOTE). */}
      {forwardTrack.length === 2 && (
        <Polyline
          positions={forwardTrack}
          pathOptions={{ color: '#22c55e', weight: 2, dashArray: '2 6', opacity: 0.8 }}
        >
          <Popup>
            <strong>PRAVAAH forward reach</strong>
            <br />
            Straight line from starting point to predicted landfall.
            <br />
            <em>
              Not a modelled drift path — the contract supplies a trajectory
              file reference, not vertices.
            </em>
          </Popup>
        </Polyline>
      )}

      {/* Predicted landfalls */}
      {landfalls.map((lf, i) =>
        lf.position ? (
          <CircleMarker
            key={`${lf.location_name}-${i}`}
            center={[lf.position.lat, lf.position.lon]}
            radius={7}
            pathOptions={{ color: '#22c55e', fillColor: '#22c55e', fillOpacity: 0.5 }}
          >
            <Popup>
              <strong>Predicted landfall</strong>
              <br />
              {lf.location_name}
              <br />
              ETA {lf.hours_until?.toFixed(1)} h · p={lf.probability?.toFixed(2)}
            </Popup>
          </CircleMarker>
        ) : null,
      )}

      {/* AIS candidates — NOT plotted (Phase 9 fix, docs/product/HONESTY_LEDGER.md
          #28). This used to render a bare <Popup> with no parent
          Marker/CircleMarker, which react-leaflet silently renders as
          nothing — a broken element, not a real feature. The real cause:
          `AISCandidateView` (the type `aisTracks` holds) carries no
          coordinates at all — `mmsi`, `vessel_name`, gap/coverage stats,
          but no lon/lat, unlike `VesselTrack`'s own point-level data
          upstream. Removed rather than left broken; extending
          `AISCandidateView` with a representative position (e.g. its last
          known point) is the real fix and is tracked, not silently
          dropped — see the module docstring's own "no invented
          coordinates" rule, which is exactly why this wasn't patched with
          a fake position instead. */}

      {/* Starting point — the decision anchor, drawn last so it sits on top */}
      {startPoint && (
        <CircleMarker
          center={startPoint}
          radius={9}
          pathOptions={{ color: '#ffffff', weight: 2, fillColor: '#dc2626', fillOpacity: 0.95 }}
        >
          <Popup>
            <strong>Starting point</strong>
            <br />
            {sp.point!.lat.toFixed(4)}°, {sp.point!.lon.toFixed(4)}°
            <br />
            source: {sp.source.replace(/_/g, ' ')}
            <br />
            land mask: {sp.land_classification.replace(/_/g, ' ')}
          </Popup>
          <Tooltip permanent direction="right" offset={[10, 0]}>
            <span style={{ fontSize: 11, fontWeight: 600 }}>
              STARTING POINT {Math.abs(sp.point!.lat).toFixed(3)}&deg;
              {sp.point!.lat >= 0 ? 'N' : 'S'} {Math.abs(sp.point!.lon).toFixed(3)}&deg;
              {sp.point!.lon >= 0 ? 'E' : 'W'}
            </span>
          </Tooltip>
        </CircleMarker>
      )}
    </MapContainer>
  )
}

export default CaseMap
