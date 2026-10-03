# AIS Acquisition Record

**Status:** Download planned and about to be executed by this document's
author (this reconciliation pass). Written before the download per
process — if the download below fails or is abandoned, this document
still records what was intended and why.

## Anchor case

`zenodo_p1_00073` (`data/raw/zenodo/extracted/part1/00073.tif`), one of 80
Gulf-of-Mexico-region scenes identified among the first 400 Zenodo Part I
scenes (verified via direct rasterio read, not filename inference):

```
bbox: lon [-92.141, -91.957], lat [19.371, 19.554]   (Bay of Campeche, Gulf of Mexico)
```

This scene is used only as a **spatial anchor** to pick a real, defensible
AIS region — not as a claim that this specific scene will be run through
the full pipeline in this pass. Its manifest entry
(`data/manifests/zenodo_part1_manifest.json`) confirms
`acquisition_date: "2000-01-01T00:00:00Z"`, i.e. a substituted dummy
timestamp with `timestamp_status: unavailable`, matching the earlier
audit finding.

## Source selected

**NOAA MarineCadastre AIS Data Handler.** Selected over other candidates
(European EMODnet, national VTMS sources) because:

1. It is the only source with a stable, unauthenticated, directly
   downloadable URL pattern —
   `https://coast.noaa.gov/htdata/CMSP/AISDataHandler/<year>/AIS_<year>_<mm>_<dd>.zip`
   — verified reachable at request time (`curl` HEAD/GET, HTTP 200).
2. It is public domain (17 U.S.C. § 105, US government work) — no license
   ambiguity, no account/credential requirement.
3. Its coverage genuinely overlaps the anchor case: the Gulf of Mexico is
   within NOAA's AIS receiver network coverage (US EEZ and approaches).

**Region:** the file is a **national daily file** covering all US coastal
AIS receiver coverage, not a Gulf-only subset — MarineCadastre does not
offer a pre-filtered regional download. A regional subset is extracted from
the national file at the derived (bronze) stage, not by requesting a
smaller raw file (none exists). The raw national file is kept as
downloaded, in full, as the immutable source.

The bronze-stage extraction bbox is `lon [-94.14,-89.96], lat
[17.37,21.55]` — a ±2° pad around the anchor case, not the full Gulf.
A first attempt at a generous full-Gulf bbox (`lon [-98,-80], lat
[18,31]`) produced ~2.4M+ in-bbox rows and OOM'd while building that many
`RawAISPoint` pydantic objects concurrently with NETRA's own training
process holding several GB of RAM. The tighter bbox is still a real,
case-anchored subset — just proportioned to what this machine can process
alongside an active training job (Phase 25).

**Date:** `2023-01-15`. `AIS_2024_01_15.zip` and later dates 404'd against
the live index at request time (server-side listing/availability lag);
`2023-01-15` was verified reachable (HTTP 200, `Content-Length:
316717207`) before committing to it. **The exact date is scientifically
arbitrary** — since the anchor case has no real acquisition timestamp
(`timestamp_status: unavailable`), no date choice could produce a genuine
temporal overlap with it. This acquisition validates the AIS
ingest/clean/canonicalize/join **pipeline** against real AIS data density
and real gap/anomaly patterns in the Gulf region, not a specific
case-to-track temporal match. `temporal_join_status` for any real
attempt against `zenodo_p1_00073` will correctly report `unavailable`
regardless of which AIS date is used.

## Expected fields (per NOAA's documented AIS Data Handler CSV schema)

`MMSI, BaseDateTime, LAT, LON, SOG, COG, Heading, VesselName, IMO,
CallSign, VesselType, Status, Length, Width, Draft, Cargo,
TransceiverClass` — covers every required canonical field (MMSI,
timestamp, lat, lon, SOG, COG, heading, vessel_type) plus useful optional
static/voyage fields (length, width, draft, nav status).

## Expected size

~317 MB compressed (verified via HTTP HEAD `Content-Length` before
download). Uncompressed CSV typically 4-6x larger for a national daily
file (~1.3-2 GB) — this stays as the raw archive; only the Gulf-region
subset is carried into a derived form.

## License

Public domain — US government work, no restriction. NOAA MarineCadastre
terms of use: https://www.fisheries.noaa.gov/foss/f?p=215:200:::NO::

## Reason selected

Only source meeting every constraint in Phase 3: real, verifiable,
unambiguous identity; auto-downloadable without credentials; license with
no ambiguity; genuine (if approximate — national, not pre-filtered)
spatial relevance to a real anchor case already present in this project's
own SAR imagery.

## Storage plan (executed after this record, per Phase 3)

1. Raw download → `D:\ROUTER(DATASETS)\_downloads\ais\AIS_2023_01_15.zip`
   (new directory, nothing overwritten).
2. SHA-256 computed on the downloaded archive.
3. Extracted CSV → `D:\ROUTER(DATASETS)\VARUNA\data\raw\ais\2023-01-15\`
   — only if that path does not already contain a file with the same
   name (checked before extraction; `data/raw/ais/` currently holds only
   `.gitkeep`, so no conflict is expected, but the check happens
   regardless).
4. Region subset written to `data/bronze/ais/` as a derived artifact —
   the national raw CSV is never modified or deleted.

## Result (executed)

The ±2° bbox around the anchor case yielded only **191 AIS records from
33 unique vessels across the full day**, producing 16 tracks after
cleaning (`data/bronze/ais/gulf_2023-01-15_summary.json`). This is real,
not a bug: the anchor case sits in the Bay of Campeche (lat ~19.4°N),
which is at the edge of — and largely outside — the primary US AIS
receiver network's coverage, which is denser along the Texas/Louisiana/
Florida coast (lat ~25-30°N). MarineCadastre's shore-based AIS receivers
do not comprehensively cover Mexican EEZ waters.

This is an honest finding about the acquisition, not a reason to widen
the bbox to manufacture more hits — a wider bbox would mean the AIS data
no longer genuinely anchors to the real case, and would reintroduce the
memory problem this narrower bbox was chosen to avoid. 16 real tracks
with real gap patterns is a small but genuine dataset, sufficient to
exercise the ingest → clean → canonicalize → join pipeline against real
data, which is this acquisition's actual purpose (pipeline validation,
not scientific attribution — see the date-arbitrariness note above).

A production deployment targeting the Arabian Sea / Bay of Bengal (ERA5's
actual domain — see `docs/datasets/ERA5_DOMAIN_POLICY.md`) would need a
different AIS source with real receiver coverage there; MarineCadastre's
US-only coverage was selected specifically because it was the one
source meeting every acquisition constraint (auto-downloadable, license-
unambiguous, verifiably reachable), not because it is the eventual
deployment-region source.
