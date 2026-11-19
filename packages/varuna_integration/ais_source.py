"""
Phase 3 - real AIS SourceAdapter.

    real AIS  ->  SourceAdapter  ->  FetchResult  ->  EvidenceMode.REAL
              ->  canonical VesselTrack  ->  CaseWorkflow / NYAYA

Real MC20 AIS already exists on disk (530 tracks in bronze, joined to the SAR
footprint in the Event Gold). Until now it was reachable only from standalone
scripts, so nothing downstream could obtain it through the one boundary that
assigns provenance. This module closes that gap: it is a genuine
`SourceAdapter`, so callers go through `fetch_with_mode()` and get REAL /
SIMULATED / UNAVAILABLE decided by what the adapter actually did.

The join-status rule this module exists to protect
--------------------------------------------------
A track can be near the slick in space and still have no AIS fix inside the
temporal window. Those are different evidentiary claims, and conflating them
manufactures attribution evidence out of geometry.

`AISJoinStatus` therefore keeps them separate and `select_tracks()` will not
return a spatially-matched-only track under a `temporally_matched` request. The
counts, the two distinct "closest vessel" figures, and each track's own status
are carried through verbatim from the Gold join - this module classifies
nothing itself.

Memory note: the bronze tracks file is ~276MB. `stream_tracks()` scans it with
a bracket-depth parser and materializes one track object at a time, so a
bounded fixture never costs a full load.
"""
from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime, timezone
from enum import StrEnum
from pathlib import Path
from typing import Iterator

from varuna_contracts.evidence import EvidenceMode, Provenance
from varuna_contracts.schemas import AISPoint, BBox, VesselTrack, VesselType
from varuna_integration.stage import StageResult, StageStatus
from varuna_source_adapters.protocol import FetchResult, SourceAdapter, SourceQuery


class AISJoinStatus(StrEnum):
    """How a track relates to the SAR observation. Deliberately not a boolean.

    TEMPORALLY_MATCHED is the only status that constitutes temporal evidence.
    SPATIALLY_MATCHED_ONLY means the vessel was in the footprint but no fix
    fell inside the window - a candidate, not a witness.
    """

    TEMPORALLY_MATCHED = "temporally_matched"
    SPATIALLY_MATCHED_ONLY = "spatially_matched_only"
    TEMPORALLY_UNAVAILABLE = "temporally_unavailable"
    NOT_MATCHED = "not_matched"

    @property
    def is_temporal_evidence(self) -> bool:
        return self is AISJoinStatus.TEMPORALLY_MATCHED


@dataclass(frozen=True)
class AISTrackJoin:
    """One track's join record, carried verbatim from the Gold join file."""

    track_id: str
    mmsi: str
    vessel_name: str | None
    n_points: int
    n_points_in_sar_footprint: int
    spatially_matched: bool
    temporally_matched: bool
    status: AISJoinStatus
    closest_distance_km: float | None
    closest_point_timestamp: str | None
    closest_time_delta_seconds: float | None

    @classmethod
    def from_record(cls, rec: dict) -> "AISTrackJoin":
        raw = str(rec.get("status", "")).strip().upper()
        if raw == "TEMPORALLY_MATCHED":
            status = AISJoinStatus.TEMPORALLY_MATCHED
        elif raw in ("SPATIALLY_MATCHED", "SPATIALLY_MATCHED_ONLY"):
            status = AISJoinStatus.SPATIALLY_MATCHED_ONLY
        elif raw in ("TEMPORALLY_UNAVAILABLE", "TEMPORAL_UNAVAILABLE"):
            status = AISJoinStatus.TEMPORALLY_UNAVAILABLE
        elif raw in ("NOT_MATCHED", ""):
            status = AISJoinStatus.NOT_MATCHED
        else:
            # An unrecognised status must never silently become the strongest
            # one. Degrade to the weakest claim and keep the raw string.
            status = AISJoinStatus.NOT_MATCHED
        # Cross-check: a record may not claim temporal matching unless its own
        # status says so. Fail closed towards the weaker claim.
        if status.is_temporal_evidence and not rec.get("temporally_matched", False):
            status = AISJoinStatus.SPATIALLY_MATCHED_ONLY
        return cls(
            track_id=rec["track_id"],
            mmsi=str(rec["mmsi"]),
            vessel_name=rec.get("vessel_name"),
            n_points=int(rec.get("n_points", 0)),
            n_points_in_sar_footprint=int(rec.get("n_points_in_sar_footprint", 0)),
            spatially_matched=bool(rec.get("spatially_matched", False)),
            temporally_matched=bool(rec.get("temporally_matched", False)),
            status=status,
            closest_distance_km=rec.get("closest_distance_km"),
            closest_point_timestamp=rec.get("closest_point_timestamp"),
            closest_time_delta_seconds=rec.get("closest_time_delta_seconds"),
        )


@dataclass(frozen=True)
class EventAISJoin:
    """The whole join file: counts and per-track status, unmodified."""

    sar_footprint: BBox
    t_sar: datetime
    window_before_hours: float
    window_after_hours: float
    n_tracks_total: int
    n_tracks_spatially_matched: int
    n_tracks_temporally_matched: int
    n_tracks_temporally_unavailable: int
    closest_temporally_matched: dict | None
    bronze_tracks_path: Path
    tracks: list[AISTrackJoin]

    @classmethod
    def load(cls, join_path: Path) -> "EventAISJoin":
        raw = json.loads(join_path.read_text(encoding="utf-8"))
        t = datetime.fromisoformat(raw["t_sar"])
        if t.tzinfo is None:
            t = t.replace(tzinfo=timezone.utc)
        return cls(
            sar_footprint=BBox(**raw["sar_footprint"]),
            t_sar=t,
            window_before_hours=float(raw["window_before_hours"]),
            window_after_hours=float(raw["window_after_hours"]),
            n_tracks_total=int(raw["n_tracks_total"]),
            n_tracks_spatially_matched=int(raw["n_tracks_spatially_matched"]),
            n_tracks_temporally_matched=int(raw["n_tracks_temporally_matched"]),
            n_tracks_temporally_unavailable=int(raw.get("n_tracks_temporally_unavailable", 0)),
            closest_temporally_matched=raw.get("closest_temporally_matched"),
            bronze_tracks_path=Path(raw["raw_source_reference"]["bronze_tracks_path"]),
            tracks=[AISTrackJoin.from_record(t) for t in raw["tracks"]],
        )

    def select(self, status: AISJoinStatus, limit: int | None = None) -> list[AISTrackJoin]:
        out = [t for t in self.tracks if t.status is status]
        out.sort(key=lambda t: (t.closest_distance_km is None, t.closest_distance_km))
        return out[:limit] if limit else out


# ------------------------------- the adapter -------------------------------

class EventAISAdapter(SourceAdapter):
    """Serves the already-acquired real AIS for one event.

    It reads from disk rather than the network - the data was fetched by the
    acquisition track and is immutable here. `is_simulated=False` is therefore
    the truth, and `fetch_with_mode()` turns that into `EvidenceMode.REAL`.
    A missing file makes `health_check()` False, which yields UNAVAILABLE; the
    adapter never substitutes mock vessels.
    """

    def __init__(self, join_path: Path, *, source_id: str = "ais.marinecadastre.event_gold"):
        self.join_path = Path(join_path)
        self._source_id = source_id
        self._join: EventAISJoin | None = None

    @property
    def source_id(self) -> str:
        return self._source_id

    def health_check(self) -> bool:
        if not self.join_path.exists():
            return False
        try:
            return self.join().bronze_tracks_path.exists()
        except Exception:
            return False

    def join(self) -> EventAISJoin:
        if self._join is None:
            self._join = EventAISJoin.load(self.join_path)
        return self._join

    def fetch(self, query: SourceQuery) -> FetchResult:
        join = self.join()
        if not join.bronze_tracks_path.exists():
            raise FileNotFoundError(
                f"AIS bronze tracks missing at {join.bronze_tracks_path}; "
                "refusing to synthesize vessel data."
            )
        return FetchResult(
            artifact_path=str(join.bronze_tracks_path),
            provenance=Provenance(
                source_id=self._source_id,
                source_version=query.product_id,
                notes=(
                    f"{join.n_tracks_total} real tracks; "
                    f"{join.n_tracks_spatially_matched} spatially matched, "
                    f"{join.n_tracks_temporally_matched} temporally matched "
                    f"(window -{join.window_before_hours}h/+{join.window_after_hours}h). "
                    "Spatial candidacy is not temporal evidence."
                ),
            ),
            is_simulated=False,
        )


# ------------------------- bronze -> canonical VesselTrack -------------------------

def stream_tracks(path: Path, wanted_track_ids: set[str] | None = None,
                  limit: int | None = None, max_bytes: int = 512 * 1024 * 1024
                  ) -> Iterator[dict]:
    """Yield top-level objects from a large `[{...},{...}]` file one at a time.

    Bracket-depth scan over the raw text; only the bytes of the current object
    are held in memory. Stops early once `limit` matches are found.
    """
    depth = 0
    buf: list[str] = []
    in_string = False
    escape = False
    started = False
    read_bytes = 0
    found = 0
    with path.open("r", encoding="utf-8") as f:
        while True:
            chunk = f.read(1024 * 1024)
            if not chunk:
                return
            read_bytes += len(chunk)
            for ch in chunk:
                if not started:
                    if ch == "[":
                        started = True
                    continue
                if depth == 0:
                    if ch in " \t\n\r,":
                        continue
                    if ch == "]":
                        return
                buf.append(ch)
                if in_string:
                    if escape:
                        escape = False
                    elif ch == "\\":
                        escape = True
                    elif ch == '"':
                        in_string = False
                    continue
                if ch == '"':
                    in_string = True
                elif ch == "{":
                    depth += 1
                elif ch == "}":
                    depth -= 1
                    if depth == 0:
                        obj = json.loads("".join(buf))
                        buf = []
                        if wanted_track_ids is None or obj.get("track_id") in wanted_track_ids:
                            yield obj
                            found += 1
                            if limit is not None and found >= limit:
                                return
            if read_bytes >= max_bytes:
                return


def to_vessel_track(raw: dict) -> VesselTrack:
    """Bronze record -> canonical `VesselTrack`. Field mapping only.

    Unknown vessel types become `VesselType.UNKNOWN` rather than a guess, and
    points that fail the contract's own bounds are dropped with the rest kept -
    a malformed fix must not silently become a plausible one.
    """
    points: list[AISPoint] = []
    for p in raw.get("points", []):
        ts = p.get("timestamp")
        if ts is None:
            continue
        t = datetime.fromisoformat(str(ts).replace("Z", "+00:00"))
        if t.tzinfo is None:
            t = t.replace(tzinfo=timezone.utc)
        try:
            points.append(AISPoint(
                timestamp=t, lon=float(p["lon"]), lat=float(p["lat"]),
                sog_knots=p.get("sog_knots"), cog_deg=p.get("cog_deg"),
                heading_deg=p.get("heading_deg"),
                interpolated=bool(p.get("interpolated", False)),
                position_std_km=float(p.get("position_std_km", 0.0) or 0.0),
            ))
        except Exception:
            continue
    try:
        vtype = VesselType(str(raw.get("vessel_type", "unknown")).lower())
    except ValueError:
        vtype = VesselType.UNKNOWN
    return VesselTrack(
        mmsi=str(raw["mmsi"]),
        imo=raw.get("imo"),
        name=raw.get("vessel_name"),
        vessel_type=vtype,
        points=points,
    )


def load_event_tracks(
    adapter: EventAISAdapter,
    query: SourceQuery,
    *,
    status: AISJoinStatus = AISJoinStatus.TEMPORALLY_MATCHED,
    limit: int = 5,
) -> StageResult:
    """The Phase-3 entry point: adapter -> FetchResult -> canonical tracks.

    Goes through `fetch_with_mode()` so provenance is decided by the adapter's
    behaviour, never by a caller's expectation. Returns tracks only for the
    requested join status - a `TEMPORALLY_MATCHED` request can never be
    satisfied with spatially-matched-only candidates.
    """
    import time

    from varuna_source_adapters.protocol import fetch_with_mode

    t0 = time.perf_counter()
    result, mode = fetch_with_mode(adapter, query)
    if result is None or mode is EvidenceMode.UNAVAILABLE:
        return StageResult(
            stage="ais_ingest", status=StageStatus.BLOCKED,
            evidence_mode=EvidenceMode.UNAVAILABLE,
            reason=(
                "AIS_UNAVAILABLE: the AIS source adapter could not serve this "
                f"event (join={adapter.join_path}). No vessel data is substituted."
            ),
            runtime_seconds=time.perf_counter() - t0,
        )

    join = adapter.join()
    selected = join.select(status, limit=limit)
    if not selected:
        return StageResult(
            stage="ais_ingest", status=StageStatus.NOT_YET_PRODUCED,
            reason=(
                f"NO_TRACKS_WITH_STATUS_{status.value.upper()}: the real join "
                f"contains {join.n_tracks_total} tracks "
                f"({join.n_tracks_spatially_matched} spatially matched, "
                f"{join.n_tracks_temporally_matched} temporally matched) but none "
                "under the requested status. Weaker-status tracks are NOT "
                "substituted."
            ),
            evidence_mode=mode,
            runtime_seconds=time.perf_counter() - t0,
            detail={"requested_status": status.value},
        )

    wanted = {t.track_id for t in selected}
    by_id = {t.track_id: t for t in selected}
    tracks: list[VesselTrack] = []
    joins: list[AISTrackJoin] = []
    for raw in stream_tracks(Path(result.artifact_path), wanted_track_ids=wanted,
                             limit=len(wanted)):
        try:
            vt = to_vessel_track(raw)
        except Exception:
            continue
        tracks.append(vt)
        joins.append(by_id[raw["track_id"]])

    if not tracks:
        return StageResult(
            stage="ais_ingest", status=StageStatus.BLOCKED,
            evidence_mode=mode,
            reason=(
                "AIS_TRACKS_UNREADABLE: the join names "
                f"{len(wanted)} track(s) but none could be parsed out of "
                f"{result.artifact_path}."
            ),
            runtime_seconds=time.perf_counter() - t0,
        )

    return StageResult(
        stage="ais_ingest", status=StageStatus.PRODUCED,
        value=tracks, evidence_mode=mode,
        runtime_seconds=time.perf_counter() - t0,
        detail={
            "requested_status": status.value,
            "n_returned": len(tracks),
            "n_tracks_total": join.n_tracks_total,
            "n_spatially_matched": join.n_tracks_spatially_matched,
            "n_temporally_matched": join.n_tracks_temporally_matched,
            "n_temporally_unavailable": join.n_tracks_temporally_unavailable,
            "closest_temporally_matched": join.closest_temporally_matched,
            "t_sar": join.t_sar.isoformat(),
            "window_before_hours": join.window_before_hours,
            "window_after_hours": join.window_after_hours,
            "track_join_status": {j.mmsi: j.status.value for j in joins},
            "source_id": adapter.source_id,
        },
    )
