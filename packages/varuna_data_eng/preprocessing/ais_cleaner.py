from datetime import UTC, datetime

from varuna_contracts.schemas import VesselType
from varuna_data_eng.schemas.ais import (
    AISGapRecord,
    CleaningAction,
    GapClass,
    RawAISPoint,
    RawAISTrack,
)
from varuna_geospatial.utils import haversine_km


class AISCleaner:
    """Cleans RawAISPoint lists and detects gaps."""

    def clean(self, points: list[RawAISPoint], mmsi: str) -> list[RawAISTrack]:
        if not points:
            return []

        # Sort by timestamp. sorted(), not points.sort() — the caller's list
        # must never be mutated by a "clean" call (real bug: the previous
        # in-place .sort() silently reordered whatever list the caller held
        # a reference to).
        points = sorted(points, key=lambda p: p.timestamp)

        cleaned_points = []
        logs = []
        flags = set()
        
        # Dedup and invalid coord rejection
        seen = set()
        for pt in points:
            if not (-180 <= pt.lon <= 180 and -90 <= pt.lat <= 90):
                logs.append(CleaningAction(action_type="REJECT", description=f"Invalid coord {pt.lon},{pt.lat}", timestamp=datetime.now(UTC)))
                continue
            
            key = (pt.timestamp.timestamp(), pt.lon, pt.lat)
            if key in seen:
                logs.append(CleaningAction(action_type="DEDUP", description=f"Duplicate point at {pt.timestamp}", timestamp=datetime.now(UTC)))
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
                logs.append(CleaningAction(action_type="SPLIT", description=f"Track split at VERY_LONG gap of {dt_minutes:.1f}m", timestamp=datetime.now(UTC)))
                # Real bug fix: the VERY_LONG gap that CAUSED this split was
                # being built and then discarded — current_gaps was reset to
                # [] on the next line without the gap ever being attached
                # anywhere, so the split boundary itself carried no gap
                # metadata. Attach it to the segment being closed (it is the
                # gap AFTER this segment's last point, which is exactly what
                # AISGapRecord.start/end already encode).
                current_gaps.append(gap)
                tracks.append(self._build_track(mmsi, current_segment, current_gaps, list(flags), logs))
                current_segment = [curr]
                current_gaps = []
                # Real bug fix: `flags` was never reset across a split, so a
                # SOG/implied-speed anomaly detected in a later segment was
                # retroactively attributed to every earlier segment's
                # `_build_track` call too (list(flags) at that point already
                # excluded later anomalies — the leak runs the OTHER
                # direction: an earlier segment's flags carry forward into
                # every later segment once first set, since the set is never
                # cleared). Reset per segment; state must not cross a split.
                flags = set()
            else:
                current_segment.append(curr)
                if gap:
                    current_gaps.append(gap)
                    
        if len(current_segment) >= 2:
            tracks.append(self._build_track(mmsi, current_segment, current_gaps, list(flags), logs))
            
        return tracks

    def _build_track(self, mmsi: str, points: list[RawAISPoint], gaps: list[AISGapRecord], flags: list[str], logs: list[CleaningAction]) -> RawAISTrack:
        # Map first point's vessel type code. `code == 0` means "Not available"
        # per the AIS Type-of-Ship spec, and `code is None` means the field was
        # absent entirely — both correctly map to UNKNOWN, so the check below
        # is written explicitly rather than relying on `if code:` being falsy
        # for 0 (that happened to give the right answer for 0, but only by
        # accident of Python truthiness — worth spelling out so a future
        # change to the code ranges below doesn't silently start treating 0
        # as OTHER).
        v_type = VesselType.UNKNOWN
        code = points[0].vessel_type_code
        if code is not None and code != 0:
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
