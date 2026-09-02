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
import type { BBoxValue, OperatorCase } from '@/lib/operator-case-types'

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

  const origin =
    oc.origin.status === 'produced'
      ? (oc.origin.value as unknown as { bbox?: BBoxValue } | null)
      : null
  const phiBbox: BBoxValue | null = origin?.bbox ?? null

  const forecast = oc.forecast.status === 'produced' ? oc.forecast.value : null
  const landfalls = forecast?.landfalls ?? []

  const aisTracks = oc.ais.status === 'produced' ? (oc.ais.value ?? []) : []

  // Collect every real coordinate the case carries, then fit to their union.
  const bounds = useMemo<LatLngBoundsExpression | null>(() => {
    const pts: [number, number][] = []
    if (startPoint) pts.push(startPoint as [number, number])
    if (detectionCentroid) pts.push([detectionCentroid.lat, detectionCentroid.lon])
    const boxes: (BBoxValue | null)[] = [detectionBbox, phiBbox]
    for (const b of boxes) {
      if (b) {
        pts.push([b.min_lat, b.min_lon])
        pts.push([b.max_lat, b.max_lon])
      }
    }
    for (const lf of landfalls) {
      if (lf.position) pts.push([lf.position.lat, lf.position.lon])
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
  }, [startPoint, detectionCentroid, detectionBbox, phiBbox, landfalls])

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

      {/* AIS candidates, only when genuinely produced */}
      {aisTracks.map((t) => (
        <Popup key={t.mmsi}>{t.vessel_name ?? t.mmsi}</Popup>
      ))}

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
