from typing import List, Tuple
from datetime import datetime, timezone
from varuna_contracts.schemas import VesselType
from varuna_data_eng.schemas.ais import RawAISPoint, RawAISTrack, AISGapRecord, GapClass, CleaningAction
from varuna_geospatial.utils import haversine_km

class AISCleaner:
    """Cleans RawAISPoint lists and detects gaps."""

    def clean(self, points: List[RawAISPoint], mmsi: str) -> List[RawAISTrack]:
        if not points:
            return []

        # Sort by timestamp
        points.sort(key=lambda p: p.timestamp)
        
        cleaned_points = []
        logs = []
        flags = set()
        
        # Dedup and invalid coord rejection
        seen = set()
        for pt in points:
            if not (-180 <= pt.lon <= 180 and -90 <= pt.lat <= 90):
                logs.append(CleaningAction(action_type="REJECT", description=f"Invalid coord {pt.lon},{pt.lat}", timestamp=datetime.now(timezone.utc)))
                continue
            
            key = (pt.timestamp.timestamp(), pt.lon, pt.lat)
            if key in seen:
                logs.append(CleaningAction(action_type="DEDUP", description=f"Duplicate point at {pt.timestamp}", timestamp=datetime.now(timezone.utc)))
                continue
            seen.add(key)
            
            # Impossible speed flag (non-HSC > 50 knots)
            if pt.sog_knots is not None and pt.sog_knots > 50.0:
                if pt.vessel_type_code not in (40, 41, 42, 43, 44, 45, 46, 47, 48, 49): # non-HSC
                    flags.add("PHYSICALLY_IMPLAUSIBLE_SOG")
            
            cleaned_points.append(pt)

        if len(cleaned_points) < 2:
            return []

        # Assemble tracks (split at VERY_LONG gaps > 24h)
        tracks = []
        current_segment = [cleaned_points[0]]
        current_gaps = []
        
        for i in range(1, len(cleaned_points)):
            prev = cleaned_points[i-1]
            curr = cleaned_points[i]
            
            dt_minutes = (curr.timestamp - prev.timestamp).total_seconds() / 60.0
            dist_km = haversine_km(prev.lon, prev.lat, curr.lon, curr.lat)
            
            # Implied speed check (> 60 knots over gap)
            implied_knots = (dist_km / (dt_minutes / 60.0)) * 0.539957 if dt_minutes > 0 else 0
            if implied_knots > 60.0:
                flags.add("IMPLIED_SPEED_IMPOSSIBLE")
                
            gap = None
            if dt_minutes < 5:
                pass
            elif dt_minutes < 30:
                gap = AISGapRecord(start=prev.timestamp, end=curr.timestamp, duration_minutes=dt_minutes, distance_km=dist_km, gap_class=GapClass.SHORT, interpolated=False, is_observable=False)
            elif dt_minutes < 360:
                gap = AISGapRecord(start=prev.timestamp, end=curr.timestamp, duration_minutes=dt_minutes, distance_km=dist_km, gap_class=GapClass.MEDIUM, interpolated=False, is_observable=False)
            elif dt_minutes <= 1440:
                gap = AISGapRecord(start=prev.timestamp, end=curr.timestamp, duration_minutes=dt_minutes, distance_km=dist_km, gap_class=GapClass.LONG, interpolated=False, is_observable=True)
            else:
                # VERY LONG -> Split
                gap = AISGapRecord(start=prev.timestamp, end=curr.timestamp, duration_minutes=dt_minutes, distance_km=dist_km, gap_class=GapClass.VERY_LONG, interpolated=False, is_observable=True)
                
            if gap and gap.gap_class == GapClass.VERY_LONG:
                logs.append(CleaningAction(action_type="SPLIT", description=f"Track split at VERY_LONG gap of {dt_minutes:.1f}m", timestamp=datetime.now(timezone.utc)))
                tracks.append(self._build_track(mmsi, current_segment, current_gaps, list(flags), logs))
                current_segment = [curr]
                current_gaps = []
            else:
                current_segment.append(curr)
                if gap:
                    current_gaps.append(gap)
                    
        if len(current_segment) >= 2:
            tracks.append(self._build_track(mmsi, current_segment, current_gaps, list(flags), logs))
            
        return tracks

    def _build_track(self, mmsi: str, points: List[RawAISPoint], gaps: List[AISGapRecord], flags: List[str], logs: List[CleaningAction]) -> RawAISTrack:
        # Map first point's vessel type code
        v_type = VesselType.UNKNOWN
        code = points[0].vessel_type_code
        if code:
            if 70 <= code <= 79: v_type = VesselType.CARGO
            elif 80 <= code <= 89: v_type = VesselType.TANKER
            elif code == 30: v_type = VesselType.FISHING
            elif 60 <= code <= 69: v_type = VesselType.PASSENGER
            elif code in (31, 32, 52): v_type = VesselType.TUG
            else: v_type = VesselType.OTHER

        return RawAISTrack(
            track_id=f"{mmsi}_{points[0].timestamp.timestamp():.0f}_{points[-1].timestamp.timestamp():.0f}",
            mmsi=mmsi,
            imo=points[0].imo,
            vessel_name=points[0].vessel_name,
            vessel_type=v_type,
            points=points,
            gaps=gaps,
            quality_flags=flags,
            cleaning_log=logs,
            provenance=points[0].provenance
        )
