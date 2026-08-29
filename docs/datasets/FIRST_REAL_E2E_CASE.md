# VARUNA GRID v2 — First Real End-to-End Case

**Status:** Decision-support document. Read-only discovery pass — no dataset
was downloaded, moved, renamed, deleted, or preprocessed to produce this
document. Nothing below is a decision; it is evidence for one.

## Objective

Determine which geographic/temporal study case is most feasible for the
first real (non-synthetic) VARUNA end-to-end demonstration:

```
SAR → NETRA → oil evidence → AIS → PRATIVARTAN → Phi → NYAYA → Validity → PRAVAAH
```

Two candidates are evaluated on evidence already on disk. A third region
was considered and rejected before formal evaluation — see the note under
Candidate B.

---

## Candidate A — Gulf of Mexico

### What exists, verified

| Requirement | Evidence |
|---|---|
| SAR observation | **Yes.** Zenodo Part I contains real Sentinel-1 GRD scenes in the Gulf of Mexico. Direct rasterio inspection of the first 400 of 1,200 scenes found 80 scenes with bounding boxes inside the Gulf (lon roughly -98 to -80, lat 18-31). Anchor scene `zenodo_p1_00073` (`data/raw/zenodo/extracted/part1/00073.tif`): bbox lon [-92.141,-91.957], lat [19.371,19.554], 2048x2048, VV/VH float32, EPSG:4326 — verified by direct file read, not filename inference. |
| SAR acquisition timestamp | **No.** `data/manifests/zenodo_part1_manifest.json` records `acquisition_date: "2000-01-01T00:00:00Z"` for every Part I scene — a substituted dummy value. The real acquisition time was not published with this dataset release and is not recoverable from the file itself (checked: no timestamp in the GeoTIFF's own metadata/tags). |
| SAR geography | **Yes.** Real EPSG:4326 bounds per scene, verified by direct read. |
| Oil detection / label | **Partial.** Binary oil masks exist for every Part I scene (paired 1:1). Whether NETRA can produce a *trained* detection is outside this document's scope — a real end-to-end case needs either a trained NETRA checkpoint or the ground-truth mask used directly as a stand-in "oil evidence" input for the non-NETRA half of the chain (PRATIVARTAN onward). Either path is viable for a first case; the ground-truth-mask path does not require NETRA training to complete first. |
| AIS vessel tracks | **Yes, real.** Acquired this project's most recent pass: NOAA MarineCadastre, `AIS_2023_01_15`, a ±2° region around the anchor scene. 191 records, 33 unique vessels, 16 tracks after cleaning (`data/bronze/ais/gulf_2023-01-15_summary.json`). Coverage is genuinely sparse — the anchor scene sits in the Bay of Campeche (Mexican waters), at the edge of the US AIS receiver network, not in its dense core. |
| AIS timestamps | **Yes, real.** Every record carries a real `BaseDateTime` (2023-01-15). |
| Wind forcing (ERA5) | **No, wrong domain.** The 3 ERA5 GRIB files on disk cover 8-20°N/70-85°E (Arabian Sea / Bay of Bengal) — verified via cfgrib read of all 3 files. Zero overlap with the Gulf of Mexico (roughly 18-31°N, -98 to -80°E). |
| Ocean current forcing (CMEMS) | **Present but insufficient**, and global (not Gulf-specific in a way that matters — the blocking issue is temporal, not spatial). Both local CMEMS files are single-timestep snapshots; confirmed via xarray (`time=1` each). Additionally, `copernicusmarine` has no configured credentials in this environment (`login(check_credentials_valid=True)` → `False`), so a real time-series pull is currently blocked regardless of region. |
| Sufficient temporal coverage | **No** — blocked by the SAR timestamp gap (see Hard Constraint Check below). |
| Sufficient spatial coverage | **Yes** for SAR+AIS (both real, both in-region). **No** for forcing (ERA5 wrong domain; CMEMS credential-blocked). |

### What Gulf would additionally require

- A new ERA5 request scoped to the Gulf of Mexico (the current files cannot be reused — wrong domain entirely, not partially).
- CMEMS credentials (blocks any region equally) plus a Gulf-scoped time-series request once credentials exist.
- An acknowledged, explicit decision on how to handle the missing SAR timestamp (see Hard Constraint Check) — this is not solved by acquiring more data; the dataset itself does not have it.

### Does the Gulf case need the current ERA5?

**NO — cannot use current ERA5 (REQUIRES NEW DOWNLOAD).** The domain does not overlap the Gulf of Mexico at all; this is not a partial-coverage problem to reconcile (unlike the 3-file ERA5 domain-split problem solved for the Indian-domain data), it is a different hemisphere of longitude entirely.

---

## Candidate B — Indian Domain (Arabian Sea / Bay of Bengal)

A third candidate — **North Sea / Mediterranean / Red Sea** (also represented in Zenodo Part I per earlier audit findings) — was considered and set aside before formal evaluation: no AIS, ERA5, or CMEMS data exists locally for any of those regions, and none is "strongly supported by data already available" per this task's instruction to only add a region under that bar. Not carried forward.

### What exists, verified

| Requirement | Evidence |
|---|---|
| SAR observation (usable, GRD) | **No — confirmed by direct scan.** A targeted rescan of the first 400 of 1,200 Part I scenes for lon 70-90°E / lat 5-25°N (direct rasterio bbox read, same method used to find the 80 Gulf-of-Mexico candidates) found **0 matches**. Consistent with the prior full audit's finding that Part I scenes are located in the Gulf of Mexico, North Sea, Mediterranean, and Red Sea — not the Arabian Sea / Bay of Bengal. |
| SAR observation (any product) | **Partial — wrong level.** 251 real Sentinel-1 archives exist at `D:\ROUTER(DATASETS)\ASF`, genuinely covering Indian territory — verified this session by reading one archive's `manifest.safe` (via zip, no extraction) and finding a real embedded footprint (lat 16.14-18.10°N, lon 77.12-79.80°E — inland southern India, Andhra Pradesh/Telangana, not ocean). These are **Level-0 RAW** (`S1{A,C,D}_IW_RAW__0SDV`), unfocused — not usable as imagery without SAR focusing (SNAP/IPF), which the current pipeline does not perform. Which of the 251 archives (if any) cover *coastal/ocean* Indian waters rather than land was not exhaustively checked this pass (would require reading 250 more manifests — cheap per-file, not done here as it exceeds this document's discovery scope). |
| SAR acquisition timestamp | **Yes, for the RAW archives** — real timestamps are embedded in the SAFE filename convention (verified: `S1A_IW_RAW__0SDV_20260511T003852_...`) and in the manifest itself. This is the one respect in which the Indian-domain SAR material is *better* than Zenodo Part I — but it is attached to the wrong product level. |
| SAR geography | **Yes, per-archive**, extractable from each archive's `manifest.safe` (proven working on one file this session), not yet done for all 251. |
| Oil detection / label | **No.** No oil masks exist for any ASF archive (masks only exist for Zenodo Part I/II, which are in different regions). Even after hypothetical SAR focusing, there is no ground-truth label for an Indian-domain scene. |
| AIS vessel tracks | **No.** No AIS data has been acquired for the Indian Ocean / Arabian Sea / Bay of Bengal region. The only real AIS on disk is the Gulf-of-Mexico-region MarineCadastre extraction, which is a US-coverage source with no data outside US receiver range. |
| AIS timestamps | **N/A** — no data. |
| Wind forcing (ERA5) | **Yes, already local.** 3 GRIB1 files, verified via cfgrib: u10/v10, hourly, continuous 2010-01-01 to 2026-08-17, reconciled usable intersection domain **8-20°N/70-85°E** per `docs/datasets/ERA5_DOMAIN_POLICY.md` (built in the prior pass from the same 3 files' differing individual bboxes). |
| Ocean current forcing (CMEMS) | **Present but insufficient**, same as Gulf — global snapshots, single timestep, credential-blocked for a real time series. The credential blocker is region-independent. |
| Sufficient temporal coverage | **No** — no SAR product with both a real timestamp *and* usable imagery exists for this region (RAW has the timestamp but not usable imagery; there is no GRD). |
| Sufficient spatial coverage | **Partial.** ERA5 covers the domain well. AIS is entirely absent. SAR (as GRD) is entirely absent; SAR (as RAW, wrong product) does cover Indian territory but coastal/ocean coverage within it is unconfirmed. |

### What Indian domain would additionally require

- Real Sentinel-1 **GRD** (or SAR focusing of the existing RAW archives — a substantial capability the pipeline does not have; flagged as out of scope for a first case).
- A real oil-spill (or at minimum, any) label source for whichever scene is chosen — none exists for this region on disk today.
- AIS acquisition for Arabian Sea / Bay of Bengal shipping lanes — an entirely new acquisition, no current source identified (the prior AIS acquisition record `docs/datasets/AIS_ACQUISITION_RECORD.md` noted MarineCadastre is US-only and explicitly is not a deployment-region source).
- CMEMS credentials + a real time-series request (same blocker as Gulf).

### Does the Indian case need new ERA5?

**NO — current ERA5 is usable as-is**, within the reconciled domain (8-20°N/70-85°E). This is the one genuine advantage this candidate has over Gulf: forcing-wind data is real, local, and already validated.

---

## Data Availability Matrix

Values are `AVAILABLE`, `PARTIAL`, `MISSING`, `BLOCKED`, or `UNKNOWN` — never inferred from a filename alone; each cell is backed by a direct read this session or the prior audit pass (see evidence tables above).

| Requirement | Gulf of Mexico | Indian Domain |
|---|---|---|
| SAR (usable product) | AVAILABLE (Zenodo Part I, GRD) | MISSING (only RAW; no GRD) |
| SAR timestamp | MISSING (dummy 2000-01-01) | PARTIAL (real, but only on the wrong product — RAW) |
| SAR labels | AVAILABLE (oil masks, Part I) | MISSING |
| AIS | AVAILABLE (real, sparse — 33 vessels, 1 day) | MISSING |
| AIS time overlap with SAR | BLOCKED (SAR has no real timestamp to overlap with) | MISSING (no AIS at all) |
| ERA5 | MISSING for this region (REQUIRES NEW DOWNLOAD) | AVAILABLE (real, local, domain-reconciled) |
| CMEMS | BLOCKED (credentials; also insufficient time series even if unblocked) | BLOCKED (same) |
| Spatial overlap (SAR+AIS+forcing all in one place) | PARTIAL (SAR+AIS yes; ERA5 no) | PARTIAL (ERA5 yes; SAR+AIS no) |
| Temporal overlap (a single real cross-source alignment) | BLOCKED | BLOCKED |
| VARUNA adapter support | PARTIAL (`Era5Adapter`/`CmemsAdapter` exist and are real; not wired into the live DI path; `MockAisAdapter` exists but the real ingest for this pass was a standalone script, not a `SourceAdapter`) | Same adapter maturity level, but with no real AIS/SAR-GRD input to feed them |
| Expected download burden | Medium (1 region-scoped ERA5 request; CMEMS credential + request, region-independent) | Medium-High (SAR GRD or a focusing capability; AIS for a new region; CMEMS same as Gulf) |
| Expected preprocessing burden | Low-Medium (AIS pipeline already proven working end-to-end on this exact region) | High (SAR focusing is a substantial new capability, or GRD acquisition; AIS pipeline would need proving against an unfamiliar region's data density/format) |
| First-case feasibility | **Higher** — 2 of 5 core inputs already real and proven; the rest are acquisition, not new capability | **Lower** — 1 of 5 core inputs already real; SAR product-level itself is a capability gap, not just a data gap |

---

## Temporal Alignment Analysis

**Neither candidate can be temporally aligned today, for different reasons.**

- **Gulf:** the SAR side has no real timestamp at all (Zenodo Part I's known, permanent limitation for this data release — it is not recoverable, only replaceable by acquiring a different SAR product with real timestamps for the same region). The AIS side genuinely has real timestamps (2023-01-15). There is nothing to align the AIS timestamps *to*.
- **Indian domain:** the SAR RAW archives do have real timestamps (verified: `20260511T003852` etc.), but there is no AIS, no GRD imagery, and no forcing-current data to align against even if a real GRD acquisition happened.

**A genuinely temporally-aligned first case requires, at minimum, a SAR product with a real acquisition timestamp.** Neither region has that paired with a usable (GRD) imagery product today. This is the single hardest fact this document surfaces.

## Spatial Alignment Analysis

- **Gulf:** SAR and AIS are already spatially co-located and proven (the AIS acquisition this project performed was deliberately anchored to a real Gulf SAR scene's bbox). Forcing (ERA5) is not co-located — zero domain overlap.
- **Indian domain:** ERA5 is spatially available across a broad, real, usable domain. SAR (RAW) does cover Indian territory, but its ocean/coastal fraction is unconfirmed; a GRD product does not exist for this domain at all. AIS is entirely absent, so there is no spatial co-location to even evaluate.

---

## Acquisition Requirements

### If Gulf is chosen

| Dataset | Provider | Product | Format | Est. size | Geographic extent | Temporal extent | Essential variables | Complexity | License/access |
|---|---|---|---|---|---|---|---|---|---|
| ERA5 (Gulf-scoped) | Copernicus CDS | reanalysis-era5-single-levels, 10m wind | GRIB/NetCDF | Tens of MB-low GB for a short window | Gulf of Mexico bbox | Whichever window, if any, is later chosen to accompany a re-dated SAR product — TBD | u10, v10 | Low (same API/library already proven working) | Free, CDS API key required (not currently configured; simpler than CMEMS's credential gap in practice, per public CDS documentation) |
| CMEMS (Gulf-scoped time series) | Copernicus Marine Service | cmems_mod_glo_phy or a Gulf-regional product | NetCDF | Tens of MB-low GB for a short regional window | Gulf of Mexico bbox | Same TBD window | uo, vo | Medium (credential setup is the blocker, not the download mechanics — reader already proven working) | Requires a free Copernicus Marine account; **not currently configured in this environment** |

### If Indian domain is chosen

| Dataset | Provider | Product | Format | Est. size | Geographic extent | Temporal extent | Essential variables | Complexity | License/access |
|---|---|---|---|---|---|---|---|---|---|
| Sentinel-1 GRD (Indian waters) | ASF or Copernicus Open Access Hub | S1x_IW_GRDH | GeoTIFF/SAFE | Hundreds of MB-few GB per scene | Arabian Sea / Bay of Bengal coastal | Any recent date with acceptable coverage — TBD | VV, VH backscatter | Medium (acquisition mechanics are known/proven for GRD elsewhere — Zenodo — but this would be a fresh source, not reused) | Free (ESA/Copernicus open data), no special credential barrier identified |
| — or — SAR focusing of existing ASF RAW | N/A (local processing) | Level-0 → Level-1 GRD | N/A | No new download; heavy local compute | Whatever the RAW archives' actual footprints turn out to cover | 2026-05-11 to 2026-07-01 (46 dates, already on disk) | N/A | **High** — requires SNAP/IPF or equivalent, a capability this pipeline does not currently have | N/A |
| AIS (Indian Ocean shipping lanes) | Unconfirmed — no unambiguous free/auto-downloadable source identified yet for this region (unlike MarineCadastre for the US) | TBD | TBD | TBD | Arabian Sea / Bay of Bengal | TBD | MMSI, timestamp, lat/lon, SOG, COG, heading | **High** — source identification alone is unresolved | Unknown — flagged, not resolved, in the prior AIS acquisition pass |
| CMEMS (Indian-scoped time series) | Copernicus Marine Service | Same product family as Gulf | NetCDF | Similar to Gulf estimate | Arabian Sea / Bay of Bengal bbox | TBD | uo, vo | Medium (same credential blocker as Gulf) | Same credential gap |

No download was performed for either table — both are acquisition specifications only, per this task's constraints.

---

## Storage Estimate

Neither candidate requires large new storage relative to what is already on disk (1.14TB free on D:, per the last catalog build). The acquisition-table estimates above (tens of MB to low GB per forcing request) are trivial. The one potentially large item is a fresh Sentinel-1 GRD acquisition for the Indian domain (hundreds of MB to a few GB per scene, and likely several scenes needed to find one with acceptable coastal coverage and a plausible oil-relevant target) — still small relative to current headroom.

## Preprocessing Estimate

- **Gulf:** Low. The AIS ingest→clean→canonicalize→join pipeline is already built and proven against this exact region (`scripts/ingest_real_ais.py`, `AISCleaner`, `find_candidate_tracks()`). A new ERA5/CMEMS request would use the already-built `forcing_readers.py`/`ForcingCube` path with no new code.
- **Indian domain:** High if SAR focusing is chosen (a real new capability); Medium if fresh GRD is acquired instead (reuses the existing GRD-reading path proven on Zenodo). AIS preprocessing would need to be re-validated against an unfamiliar region's traffic density and data quality — the current `AISCleaner` fixes were validated only against Gulf data this session.

## Integration Complexity

Both candidates reuse the same already-built boundary code (`ForcingCube`, `CubeBackedCurrentField`/`CubeBackedWindField`, `find_candidate_tracks()`, `PrativartanService.reconstruct_origin(current=, wind=)`) — none of that is region-specific. The complexity difference between candidates is entirely in **data acquisition and SAR product-level**, not in VARUNA's own integration code.

## Scientific Relevance

**MEASURED / INFERRED / ESTIMATED, explicitly separated:**

- **MEASURED:** VARUNA's project documentation and ERA5 domain choice both target an Indian-waters deployment context (the `data/raw/era5` files were originally acquired for this domain, not for the Gulf — inferred from the fact that they were on disk before this project's AIS work began and match no other dataset's region). Gulf of Mexico has no equivalent documented deployment relevance in this project; its selection this session was purely opportunistic (Zenodo happens to contain Gulf scenes, and MarineCadastre happens to be the one easily-acquirable AIS source).
- **INFERRED:** the Indian domain is the eventual, intended deployment target; the Gulf is not.
- **ESTIMATED:** a Gulf-based first case would prove the *pipeline* (ingest, clean, join, forcing boundary, provenance propagation) faster and cheaper, but would not itself constitute evidence toward the deployment-relevant claim. An Indian-domain first case, if achieved, would be doubly valuable (pipeline proof + deployment relevance) but costs substantially more to reach.

### Scoring (1-5, 5 = best; transparent, unweighted — presented as a profile, not a single blended score, since the two axes that matter most, feasibility and relevance, pull in opposite directions and averaging them would hide that tension)

| Criterion | Gulf | Indian | Basis |
|---|---|---|---|
| 1. Real data availability | 4 | 2 | MEASURED — Gulf has 2 of 5 core real inputs (SAR, AIS) proven on disk; Indian has 1 (ERA5) |
| 2. Temporal alignment feasibility | 1 | 2 | MEASURED — Gulf's SAR has zero recoverable timestamp; Indian's SAR-RAW has one but on the wrong product, so a real GRD acquisition would carry a timestamp from day one |
| 3. Spatial alignment feasibility | 4 | 2 | MEASURED — Gulf: SAR+AIS already co-located; Indian: only ERA5 has anything to be co-located with |
| 4. AIS availability | 5 | 1 | MEASURED — Gulf: real, downloaded, tested; Indian: no source even identified |
| 5. Forcing availability | 2 | 5 | MEASURED — Gulf: wrong domain, needs new download; Indian: real, local, already domain-reconciled |
| 6. SAR availability (usable product) | 5 | 1 | MEASURED — Gulf: real GRD with labels; Indian: RAW only, wrong level, no labels |
| 7. Preprocessing complexity (lower is easier; scored inverted so 5=easiest) | 4 | 2 | ESTIMATED — Gulf reuses proven pipeline as-is; Indian needs either a new SAR-focusing capability or a fresh GRD source integration |
| 8. Storage cost (lower is easier; scored inverted) | 5 | 4 | ESTIMATED — both cheap; Indian marginally larger if fresh GRD scenes are needed |
| 9. Integration complexity (lower is easier; scored inverted) | 5 | 5 | MEASURED — identical, region-agnostic boundary code for both |
| 10. Relevance to VARUNA's deployment target | 2 | 5 | INFERRED — see Scientific Relevance above |

Row-by-row profile, not summed — see Primary Recommendation for how these are weighed.

---

## Hard Constraint Check

**Can one real SAR observation be temporally aligned with AIS, ERA5, and CMEMS, for either candidate?**

**Gulf of Mexico: NO.**
Missing: the SAR acquisition timestamp itself. `zenodo_p1_00073` and every other Part I scene records `acquisition_date: 2000-01-01T00:00:00Z`, an explicit placeholder (`timestamp_status: unavailable` elsewhere in the pipeline's own provenance handling). There is no metadata anywhere in the GeoTIFF or its accompanying files that recovers the real date. AIS *does* have real timestamps (2023-01-15) but there is nothing on the SAR side to align them to.

**Indian Domain: NO.**
Missing: a usable (GRD) SAR product entirely — the RAW archives have real timestamps but are not imagery. Missing: any AIS data for the region. Even ERA5, which is real and covers the domain, has nothing on the SAR/AIS side to align against.

**Per the instruction that a candidate is not fully feasible if temporal alignment is impossible: neither candidate is fully feasible today.** Both require closing a specific, identified gap before a genuinely temporally-aligned first case is possible — Gulf needs a re-dated (or newly acquired, timestamped) SAR source for the same region; Indian domain needs a GRD product (new acquisition or a focusing capability) plus AIS.

---

## First-Case Design (hypothetical specifications, evidence-gated)

### Gulf of Mexico

```
Region:                Gulf of Mexico / Bay of Campeche
SAR source:            Zenodo Part I (existing) — OR a freshly-acquired,
                        timestamped Sentinel-1 GRD scene over the same
                        footprint if temporal alignment is required
SAR product:            GRD, VV/VH (existing scenes confirmed)
Expected observation time: UNKNOWN/TBD (Zenodo Part I has none; a fresh
                        acquisition would need a specific date chosen by
                        the science lead)
AIS source:             NOAA MarineCadastre (proven this session)
AIS window:             TBD — would be chosen to match whatever SAR
                        timestamp is eventually available, not fixed to
                        2023-01-15 (that date was arbitrary, chosen only
                        for pipeline validation)
ERA5:                   REQUIRES NEW DOWNLOAD, Gulf-scoped
CMEMS:                  BLOCKED on credentials; Gulf-scoped once unblocked
Spatial extent:         Bay of Campeche / wider Gulf, TBD exact bbox
                        pending final scene selection
Temporal extent:        TBD — pending SAR timestamp resolution
Expected preprocessing: Low (pipeline proven); TBD exact effort pending
                        final scene/date choice
Expected storage:       Low (existing SAR reused, or a few GB for a fresh
                        scene; forcing requests are small)
```

### Indian Domain

```
Region:                 Arabian Sea or Bay of Bengal — UNKNOWN/TBD which,
                         pending a specific coastal scene choice
SAR source:              UNKNOWN/TBD — ASF RAW archives (needs focusing) or
                         a freshly-acquired GRD scene
SAR product:             UNKNOWN/TBD (RAW exists; GRD does not)
Expected observation time: Real timestamps exist in the RAW archives
                         (2026-05-11 to 2026-07-01, 46 dates) IF that
                         product level is used; TBD for any GRD alternative
AIS source:              UNKNOWN — no source identified this pass
AIS window:              TBD
ERA5:                    Already available, domain-reconciled
                         (8-20°N/70-85°E, docs/datasets/ERA5_DOMAIN_POLICY.md)
CMEMS:                   BLOCKED on credentials; region-scoped once unblocked
Spatial extent:          TBD — pending which coastal scene(s), if any, the
                         251 ASF archives' footprints actually cover
Temporal extent:         TBD
Expected preprocessing:  High (SAR focusing capability gap) or Medium
                         (fresh GRD acquisition, reusing existing readers)
Expected storage:        Low-Medium
```

---

## Primary Recommendation

**RECOMMENDATION FOR SCIENCE-LEAD REVIEW**

### Primary: Gulf of Mexico

**Why primary is easier:** Two of the five core real-data requirements (SAR
imagery+labels, AIS) are already on disk, verified, and pipeline-tested
end-to-end this session. The remaining gaps (ERA5 for this region, CMEMS
credentials) are acquisition tasks against already-working code paths, not
new capabilities. No new capability (like SAR focusing) is required.

### Backup: Indian Domain

**Why backup is viable:** It is the deployment-relevant region, and its
forcing-wind data (ERA5) is the most mature real input of either
candidate — already reconciled and validated. If the science lead
prioritizes deployment relevance over speed-to-first-case, this is the
correct fallback, accepting a materially higher acquisition and
preprocessing burden (SAR product-level gap, no AIS source identified yet).

### What would change the decision

- If a timestamped Gulf-of-Mexico Sentinel-1 GRD source becomes available
  (resolving Gulf's one hardest blocker), Gulf becomes close to fully
  feasible with only forcing-data acquisition remaining.
- If a real Indian-Ocean AIS source is identified with the same ease as
  MarineCadastre, and either fresh GRD or a SAR-focusing capability is
  authorized, Indian domain's remaining gaps narrow to acquisition effort
  comparable to Gulf's.
- If the project's near-term goal is explicitly "prove the pipeline
  connects end-to-end on real data" rather than "produce a
  deployment-relevant result," Gulf is the unambiguous choice regardless
  of the above.

---

## MUST ACQUIRE (for Primary — Gulf of Mexico)

| Dataset | Exact product | Region | Time window | Format | Reason |
|---|---|---|---|---|---|
| ERA5 | reanalysis-era5-single-levels, 10m_u/v_component_of_wind | Gulf of Mexico bbox | TBD — pending SAR timestamp decision | GRIB/NetCDF | Current ERA5 files have zero domain overlap with the Gulf |
| CMEMS | cmems_mod_glo_phy (or regional equivalent), time series not snapshot | Gulf of Mexico bbox | TBD, matching ERA5 window | NetCDF | Current CMEMS files are single-timestep; credentials also required first |
| (Conditional) A timestamped Sentinel-1 GRD source for the Gulf | Sentinel-1 GRD | Same footprint as chosen anchor scene | Any real, known date | SAFE/GeoTIFF | Only needed if genuine temporal alignment (not just spatial pipeline-proof) is required for the first case |

## ALREADY AVAILABLE (for Primary — Gulf of Mexico)

| Dataset | Exact path | Usable status |
|---|---|---|
| Zenodo Part I SAR + oil masks | `data/raw/zenodo/extracted/part1/` | Usable for spatial pipeline-proof; not usable for temporal alignment (no real timestamp) |
| Real AIS (Gulf, 2023-01-15) | `data/raw/ais/2023-01-15/AIS_2023_01_15.csv`, derived `data/bronze/ais/gulf_2023-01-15_tracks.json` | Usable, tested end-to-end against the anchor scene this session |
| AIS ingest/clean/join pipeline | `scripts/ingest_real_ais.py`, `packages/varuna_data_eng/preprocessing/ais_cleaner.py`, `packages/varuna_geospatial/ais_join.py` | Proven working on real data |
| Forcing boundary code | `packages/varuna_source_adapters/forcing_readers.py`, `packages/varuna_data_eng/schemas/forcing.py`, `packages/varuna_prativartan/cube_field.py`, `packages/varuna_pravaah/cube_provider.py` | Proven working on real ERA5 files (wrong region) and structurally against synthetic CMEMS-shaped data; ready to point at new Gulf-scoped downloads once acquired |

## NOT NEEDED for first case

| Dataset | Reason |
|---|---|
| ASF Sentinel-1 RAW (Indian domain) | Not the chosen region for Primary; also wrong product level regardless |
| xView3 | CHHAYA architecture decision (existing ADR) does not require it |
| Zenodo Part III / ESSD | Reserved for held-out evaluation, not a first pipeline-proof case |
| Bhoonidhi / NISAR / RISAT | Cross-sensor evaluation, not relevant to a first single-source case |

## FUTURE

| Dataset | Reason |
|---|---|
| Indian-domain AIS | Needed if/when Backup (Indian Domain) is authorized; no source identified yet |
| Sentinel-1 GRD (Indian waters) or a SAR-focusing capability | Needed if/when Backup is authorized |
| A timestamped Gulf SAR source | Needed if Primary is authorized AND genuine temporal alignment (not just spatial pipeline-proof) is required |
| CMEMS credentials | Needed regardless of which candidate is chosen — the single blocker common to both |

---

## Known Blockers

1. **CMEMS credentials** — blocks both candidates equally. `copernicusmarine` is installed; no account is configured in this environment. This is an operator action, not an engineering one.
2. **Zenodo Part I has no recoverable SAR timestamp** — a permanent property of that dataset release, not something further inspection will change. Blocks genuine temporal alignment for Gulf specifically.
3. **No Sentinel-1 GRD exists for the Indian domain** — only Level-0 RAW, which requires a focusing capability the pipeline does not have. Blocks Indian domain specifically.
4. **No AIS source identified for the Indian Ocean** — MarineCadastre (used for Gulf) is US-only by design. Blocks Indian domain specifically.
5. **ERA5 for the Gulf does not exist locally** — a new, region-scoped acquisition, not a reconciliation of existing files (unlike the Indian-domain ERA5 3-bbox situation, which was resolved without a new download).

## Decision Required From Science Lead

1. **Region:** Gulf of Mexico (primary, recommended) or Indian Domain (backup) — or explicitly defer both pending blocker resolution.
2. **Temporal-alignment standard:** is a case that proves the pipeline spatially and structurally, but explicitly and honestly reports `temporal_join_status=unavailable` (as the current real AIS join already does against the Gulf anchor scene), an acceptable "first real end-to-end case" — or is genuine cross-source temporal alignment a hard requirement before this milestone is considered met? This determines whether Gulf is achievable now (modulo the two acquisition items above) or requires first solving the unrecoverable-timestamp problem via a new, differently-sourced SAR acquisition.
3. **CMEMS credentials:** who provisions a Copernicus Marine account, and when — this blocks PRATIVARTAN/PRAVAAH's current-forcing input for either region.
4. **If Indian Domain is preferred despite the larger gap:** authorize either a SAR-focusing capability build-out or a fresh Sentinel-1 GRD acquisition, and begin AIS-source identification for the region — both are prerequisite research/acquisition tasks, not immediate downloads.

---

## Final Table

| Candidate | SAR | Timestamp | AIS | ERA5 | CMEMS | Spatial Alignment | Temporal Alignment | Acquisition Burden | Preprocessing Burden | E2E Feasibility |
|---|---|---|---|---|---|---|---|---|---|---|
| Gulf of Mexico | AVAILABLE | MISSING | AVAILABLE | MISSING (new download) | BLOCKED | PARTIAL | BLOCKED | Medium | Low | Higher (spatial/pipeline-proof achievable now; temporal alignment blocked) |
| Indian Domain | PARTIAL (wrong product) | PARTIAL (on wrong product) | MISSING | AVAILABLE | BLOCKED | PARTIAL | BLOCKED | Medium-High | High | Lower (forcing ready; SAR+AIS both real capability/acquisition gaps) |

---

## FINAL STATUS

**CASE DEFINITION = WAITING FOR SCIENCE-LEAD DECISION**
