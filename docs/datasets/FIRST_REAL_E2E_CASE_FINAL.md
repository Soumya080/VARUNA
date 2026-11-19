# VARUNA GRID v2 — First Real End-to-End Case (Final)

**Supersedes:** this document builds on `docs/datasets/FIRST_REAL_E2E_CASE.md`
(the earlier discovery-phase document, left unmodified) with real, dated,
event-anchored candidates in both regions, plus newly-discovered
non-data blockers that apply regardless of region.

## 1. Executive Verdict

**NO-GO for a complete real end-to-end run today.** Not because a
scientifically strong candidate doesn't exist — a genuinely strong one
does, in the Gulf — but because two independent blockers apply
regardless of which region or event is chosen:

1. **Both real-imagery sources require credentials this environment does
   not have.** Confirmed this pass by direct, unbypassed authentication
   tests: Copernicus Marine (CMEMS) returns "No credentials found";
   Copernicus Data Space (Sentinel-1 GRD download) returns
   **HTTP 401 Unauthorized** on an actual byte-range GET (catalog
   *search* is free and unauthenticated — that is how the candidates
   below were found — but *download* is not).
2. **The validity gate itself is currently unconditionally blocking,
   independent of data quality.** Per `docs/adr/ADR-0007-phi-sensitivity-design.md`
   (Track 2, landed since the prior document was written): the real
   Φ-sensitivity sweep mechanics now exist and run against real inputs,
   but the conversion from the sweep's raw output into the
   `SensitivityBlock` scalars the gate reads has not been ratified.
   `PhiField.sensitivity` stays `None`, and the gate reports
   `PHI_DIAGNOSTICS_UNAVAILABLE` (blocking) for every case — real,
   synthetic, or otherwise. This is a methodology decision outside this
   track's scope, not a data gap.

**What is genuinely new and strong:** a real, dated, precisely-located
Gulf of Mexico candidate event (MC20 / Taylor Energy) with a real
Sentinel-1 GRD scene identified for the same calendar day as an
AIS extraction already performed from already-downloaded raw data,
yielding **304,960 real AIS records, 530 real vessel tracks**, and a
closest real vessel **3.26 km from the site, 17 minutes after the SAR
acquisition**. This is the strongest real multimodal intersection found
in this project to date. It is acquisition-ready, not yet acquired
(imagery itself blocked on the same credential issue above).

## 2. Current Repository/Data State

Branch `feat/netra-real-training`, HEAD at session start
`397a90cc34b6b958d8134dc44054e08fdaf3f9f1`. Three concurrent
workstreams confirmed active via `git log --oneline -10` and file
ownership inspection:
- **NETRA training** — 12 modified + 10 untracked files, unchanged
  throughout this pass; live process confirmed running (PID 1496/58256,
  epoch 21/50 at last check, loss trending normally).
- **Track 2 (core-system/provenance)** — 3 new commits since the prior
  data-track pass: `feat(provenance): propagate evidence mode through
  adapters`, `fix(nyaya): remove fabricated prior outputs`,
  `feat(prativartan): implement genuine phi sensitivity sweep mechanics`
  (ADR-0007). Not touched by this pass.
- **Data track (this document's author)** — prior commits
  `2d3e1b3`/`7d515ba`, extended by this pass.

No collision detected. No file belonging to another workstream was
modified.

## 3. Candidate Cases

Two real, dated, precisely-located event candidates were identified this
pass (Section 4/5), replacing the earlier document's arbitrary
Zenodo-scene anchor (which had no real timestamp and could never satisfy
temporal alignment).

## 4. Gulf Feasibility — MC20 / Taylor Energy site

**Site:** Mississippi Canyon Block 20 (MC20), 28.936°N, 88.970°W — the
former Taylor Energy platform, toppled by Hurricane Ivan in 2004, since
documented as a persistent/chronic oil-slick site in NOAA/BSEE
monitoring and in peer-reviewed remote-sensing literature (a published
deep-learning study analyzed 154 real Sentinel-1 scenes 2016–2021 at
this exact site and reported a cumulative 2,564.22 km² of detected oil).
**MEASURED**, sourced from NOAA/BSEE incident records and the cited
study — not a filename or convenience guess.

**Real SAR identified (catalog-verified, not yet downloaded):**
`S1A_IW_GRDH_1SDV_20230115T000206_20230115T000231_046787_059BFF_44F2.SAFE`
— Sentinel-1A, IW, GRD, dual-pol (VV+VH), acquisition start
`2023-01-15T00:02:06.898Z`, 1,741,458,044 bytes (1.74GB), confirmed via
direct Copernicus Data Space OData catalog query intersecting the exact
MC20 point.

**Real AIS (already extracted from already-downloaded raw data, no new
download):** `data/raw/ais/2023-01-15/AIS_2023_01_15.csv` (the same
national file acquired in an earlier pass) re-filtered this pass to a
±1° box around MC20 (`scripts/ingest_real_ais_mc20.py`,
`data/bronze/ais/mc20_2023-01-15_{summary,tracks}.json`):
**304,960 in-bbox records, 535 unique vessels, 530 tracks after
cleaning** (6,705 gaps: 6,286 SHORT, 387 MEDIUM, 32 LONG).

**ERA5:** MC20 (lon −88.970) is **outside** the existing reconciled
domain (70–85°E) — requires a new, region-scoped download. Not
attempted this pass (deferred pending region selection, per policy).

**CMEMS:** blocked on credentials, region-independent.

## 5. Indian Feasibility — 2017 Ennore (Chennai) tanker collision

**Event:** collision between LPG tanker *BW Maple* and chemical tanker
*Dawn Kanchipuram*, 28 January 2017, ~04:00 local time, ~196MT bunker
fuel spilled, 2 nautical miles off Kamarajar Port, Ennore, Chennai —
a real, dated, well-documented incident (Wikipedia, IEEE Xplore
assessment paper, ScienceDirect case study, contemporary press). Exact
coordinates: **13.228°N, 80.363°E**. **MEASURED** from multiple
independent published sources.

**Real SAR identified (catalog-verified, not downloaded):**
`S1A_IW_GRDH_1SDV_20170129T003132_20170129T003157_015039_01892E_6D04.SAFE`
— Sentinel-1A, IW, GRD, dual-pol, acquisition `2017-01-29T00:31:32.651Z`,
one day after the collision, confirmed intersecting the exact collision
coordinates via the same Copernicus catalog query method. Size not
queried this pass (not yet a downloaded candidate given the credential
block applies identically here).

**ERA5:** Ennore (80.363°E, 13.228°N) is **inside** the existing
reconciled domain (70–85°E, 8–20°N) — **no new ERA5 download required**,
the one clear advantage this candidate retains over Gulf.

**AIS:** **No source identified.** MarineCadastre (used for Gulf) is
US-only by design and does not cover Indian waters. No regional
equivalent was identified in this or the prior pass. This remains the
single largest gap for this candidate — worse than in the prior
document, because now a *specific* real event with *known vessel
identities* (BW Maple, Dawn Kanchipuram) exists to match against, and
still no acquirable source exists for it.

**A site-selection dead end worth recording:** Mumbai High
(19.417°N, 71.333°E), the obvious `chronic-site` analog to MC20 for
Indian waters, was checked directly against the Copernicus catalog and
returned **zero** Sentinel-1 GRD products at any date — ESA's IW
acquisition mask does not routinely cover that specific open-ocean
point, confirmed by contrast with real, current coverage 15km away at
the Mumbai coastline. Ennore was selected instead specifically because
it is close to shore, where coverage is confirmed real.

**CMEMS:** blocked on credentials, same as Gulf.

## 6. Candidate Event Table

| Dimension | MC20 (Gulf) | Ennore (Indian) |
|---|---|---|
| SAR availability | PASS (catalog-confirmed, not downloaded) | PASS (catalog-confirmed, not downloaded) |
| SAR timestamp quality | PASS — exact, same calendar day as existing AIS | PASS — exact, 1 day after the event |
| Oil-spill evidence | PASS (peer-reviewed literature, chronic site) | PASS (multiple independent press/academic sources) |
| AIS availability | PASS — real, already extracted, 304,960 records | **FAIL** — no source identified |
| AIS temporal match | PASS — 38,244 real points within ±3h of SAR pass | FAIL (no AIS at all) |
| AIS spatial match | PASS — closest real vessel 3.26km, 17min offset | FAIL (no AIS at all) |
| ERA5 availability | **FAIL** — outside existing domain, new download required | PASS — inside existing reconciled domain |
| CMEMS availability | FAIL — credential-blocked | FAIL — credential-blocked (identical) |
| Spatial coherence | PASS (SAR∩AIS confirmed with real numbers) | PARTIAL (SAR∩ERA5 only; no AIS to intersect) |
| Temporal coherence | PASS (quantified, see Section 11) | PARTIAL (SAR date known; no AIS to align) |
| Provenance quality | PASS — every claim traced to a named source | PASS — every claim traced to a named source |
| Acquisition complexity | Medium (1 SAR scene + region-scoped ERA5, both credential/registration-gated) | Medium-High (1 SAR scene + AIS source identification, both gated/unresolved) |
| Storage cost | Low (~1.74GB SAR + small ERA5 subset) | Low (SAR unqueried; no other cost since AIS unavailable) |
| Reproducibility | PASS — exact product IDs, exact bbox, exact script | PASS — exact product ID, exact coordinates |
| Scientific value | High — chronic, extensively pre-validated in literature | High — a genuine documented spill, not a chronic seep |

## 7. SAR Availability

Both candidates: real, catalog-confirmed, **not downloaded** — blocked
on Copernicus Data Space credentials (HTTP 401, confirmed this pass, not
bypassed). Catalog *search* required no authentication; catalog
*download* does.

## 8. AIS Availability

MC20: PASS, real, already extracted from already-downloaded raw data.
Ennore: FAIL, no source identified for Indian waters (unchanged finding
from the prior document, now sharper because a specific real event with
known vessels exists to search against and none was found).

## 9. ERA5 Availability

MC20: FAIL (outside domain). Ennore: PASS (inside domain). This is the
one dimension where Ennore is strictly better than MC20.

## 10. CMEMS Availability

Both: FAIL, identically. Credentials absent, confirmed via
`copernicusmarine.login(check_credentials_valid=True)` → `False`, not
bypassed.

## 11. Temporal Alignment

**MC20 (quantified, computed this pass from real data):**
```
T_SAR  = 2023-01-15T00:02:06.898Z   (Copernicus catalog, confirmed real)
T_AIS  = 2023-01-15T00:00:00Z – 23:59:59Z  (full day, already on disk)
Closest real AIS point to MC20 within +/-3h of T_SAR:
    MMSI 368181750, 2023-01-15T00:19:04Z, 3.26 km from site
    -> offset from T_SAR: +16 min 57 sec
Points within +/-3h window: 38,244 (out of 304,960 total in-bbox for the day)
```
This is a scientifically acceptable join: a real vessel within ~3km of
the site, 17 minutes after the SAR pass, is a genuine, quantified,
close temporal-spatial coincidence — not "approximately same time"
asserted without numbers.

T_ERA5/T_CMEMS: not applicable yet — ERA5 not yet acquired for this
domain, CMEMS blocked.

**Ennore:**
```
T_SAR   = 2017-01-29T00:31:32.651Z (1 day after the 28-Jan collision)
T_AIS   = UNAVAILABLE (no source)
T_ERA5  = hourly, real, already on disk, domain covers this point
T_CMEMS = UNAVAILABLE (credential-blocked)
```
Temporal alignment cannot be assessed against AIS or CMEMS —
**UNAVAILABLE**, not guessed, not silently treated as PASS.

## 12. Spatial Alignment

**MC20:**
```
SAR ∩ AIS:              non-empty, confirmed (304,960 real AIS points
                         inside the SAR scene's approximate IW swath
                         footprint of ~250km, of which 38,244 fall
                         within +/-3h of the pass; closest point 3.26km
                         from the anchor coordinate)
SAR ∩ ERA5:              N/A (ERA5 not covering this region)
SAR ∩ CMEMS:             N/A (CMEMS blocked)
SAR ∩ AIS ∩ ERA5 ∩ CMEMS: EMPTY — not all four modalities are
                         simultaneously available for this site today
```

**Ennore:**
```
SAR ∩ ERA5:              non-empty (both cover 13.228N/80.363E)
SAR ∩ AIS:               N/A (no AIS)
SAR ∩ CMEMS:              N/A (CMEMS blocked)
SAR ∩ AIS ∩ ERA5 ∩ CMEMS: EMPTY
```

**Neither candidate achieves a non-empty four-way intersection today.**
Per Section 11's instruction, this is stated plainly rather than papered
over — the honest state is that MC20 achieves a strong **three-way**
partial (SAR+AIS confirmed; ERA5/CMEMS both pending/blocked for
independent reasons), and Ennore achieves a weaker partial (SAR+ERA5
only).

## 13. Provenance

Every factual claim in this document traces to a named, independently
checkable source: NOAA/BSEE incident records and a cited peer-reviewed
study (MC20); Wikipedia + IEEE + ScienceDirect + contemporary press
(Ennore); direct Copernicus Data Space OData catalog queries (both SAR
identifications, including the exact product ID, exact timestamp, and
exact byte size for MC20's scene); direct code execution against
already-downloaded raw AIS data (the 304,960/535/530/3.26km/17min
figures). Nothing in this document is asserted from memory alone without
a check performed this pass.

## 14. Data Quality

MC20 AIS extraction: 0 invalid/unparseable rows out of 304,960 in-bbox
(the sentinel-value normalization fix from the prior pass, `Heading=511`
→ `None`, applied automatically since it reuses `ingest_real_ais.py`'s
`_row_to_point`). Gap distribution (6,286 SHORT / 387 MEDIUM / 32 LONG)
is consistent with normal AIS reporting cadence for a busy shipping
lane, not an anomaly.

## 15. Storage Requirements

MC20 SAR (if acquired): 1.74GB. Ennore SAR (if acquired): unqueried,
plausibly similar (~1.5–2GB, typical IW GRD size). MC20-region ERA5
(if acquired): plausibly tens to low hundreds of MB (per
`docs/datasets/CMEMS_ACQUISITION_READY.md`'s analogous estimate for a
regional CMEMS request — not independently re-estimated for ERA5 this
pass). Both trivial against ~1.06TB free on D: (confirmed this pass).

## 16. Acquisition Requirements

**If MC20/Gulf proceeds** (once Copernicus Data Space credentials
exist): download the one identified 1.74GB SAR scene by its confirmed
product ID; separately request a Gulf-of-Mexico-scoped ERA5 subset (new
acquisition, domain confirmed non-overlapping with existing files).
CMEMS remains blocked independently.

**If Ennore/Indian proceeds** (same credential prerequisite): download
the one identified SAR scene; reuse existing ERA5 (no new download);
AIS acquisition path remains **unidentified** — this is a research task
(finding a real, unambiguous, licensable Indian-Ocean AIS source), not a
mechanical download, and was not resolved this pass.

## 17. Preprocessing Requirements

MC20: AIS preprocessing already complete and proven
(`ingest_real_ais_mc20.py`, reusing the bug-fixed `AISCleaner`). SAR
preprocessing (calibration/normalization to match NETRA's VV/VH dB-scale
convention) not yet designed for a full-scene GRD product — Zenodo's
tiles arrive pre-cropped to 2048×2048; a fresh full IW scene
(~25,000×16,700px) needs a cropping/calibration step this project has
not yet built for a live acquisition, only for the static Zenodo corpus.

Ennore: no AIS preprocessing possible (no data). SAR preprocessing: same
gap as MC20.

## 18. Event Gold Design

Not built this pass — correctly gated behind actual data acquisition,
which is itself gated behind the credential blockers above. The
recommended structure from the task specification
(`data/gold/varuna_event_v0_1/{sar,ais,era5,cmems,metadata,provenance,diagnostics}/`
plus a manifest) is adopted in principle for whichever candidate is
authorized, once its SAR and (for MC20) ERA5 are actually on disk. Not
scaffolded prematurely — an empty Gold directory with no real content
would be exactly the kind of fake completeness Section 25 forbids.

## 19. Scientific Risks

- **The validity-gate blocker (Section 1) is independent of which
  candidate is chosen** — even a perfect four-way real data intersection
  would still report `PHI_DIAGNOSTICS_UNAVAILABLE` today.
- MC20 is a *chronic* seep, not a single bounded event — real oil
  presence on any given SAR pass is well-precedented in the literature
  but not certain for this *specific* scene without visual/algorithmic
  confirmation post-acquisition (not fabricated as "confirmed" here).
- Ennore's AIS gap may be permanent for this project's current
  acquisition-policy constraints (auto-downloadable, unambiguous,
  license-clear sources only) — Indian-Ocean AIS aggregators identified
  in earlier passes were commercial/credentialed, not free.

## 20. Engineering Risks

- No live GRD→calibrated-array pipeline exists for a *freshly acquired*
  full Sentinel-1 scene (only for the pre-processed Zenodo corpus).
- The MC20 AIS re-extraction script (`ingest_real_ais_mc20.py`) is a
  parameterized copy of the earlier pass's script via monkeypatching —
  functional and tested against real output this pass, but a proper
  refactor (parameterize `ingest_real_ais.py` directly rather than
  monkeypatch it) would be cleaner if this pattern is reused again for a
  third region.

## 21. Primary Case

**MC20 / Taylor Energy, Gulf of Mexico.** Strongest real, quantified,
multimodal intersection found in this project: real SAR (catalog-
confirmed), real AIS (304,960 records, already extracted from
already-downloaded data, 3.26km/17min closest real match), real
peer-reviewed prior evidence of oil presence at this exact site. ERA5 is
the one gap, and it is a mechanical acquisition (once credentials
exist), not a research problem like Ennore's AIS gap.

## 22. Backup Case

**Ennore, Indian Domain.** Real, well-documented, precisely-dated event;
ERA5 already covers it with zero new acquisition. Held back to backup
status by one unresolved research gap (no AIS source) that Gulf does not
share.

## 23. Exact Missing Datasets

**For MC20 (Primary):**
- Sentinel-1 GRD scene `S1A_IW_GRDH_1SDV_20230115T000206_...` (1.74GB) — identity confirmed, download blocked on credentials
- Gulf-of-Mexico-scoped ERA5 (new acquisition, not yet specified in detail — domain and dates would mirror the MC20/AIS window)
- CMEMS regional time series (credential-blocked, independent of region)

**For Ennore (Backup):**
- Sentinel-1 GRD scene `S1A_IW_GRDH_1SDV_20170129T003132_...` — identity confirmed, download blocked on credentials
- Indian-Ocean AIS source — **not identified**, a research task
- CMEMS regional time series (same credential block)

## 24. Exact Acquisition Plan

1. Operator provisions a Copernicus Data Space account (free registration) and, separately, a Copernicus Marine account (CMEMS) — these are confirmed to be two distinct authentication systems requiring two distinct sets of credentials in this environment; not verified whether a single Copernicus SSO account eventually unifies them.
2. Once Data Space credentials exist: download the one identified MC20 SAR scene by its exact product ID (`6fc676ba-b961-5bfc-9211-8076f8f1481c`), to `D:\ROUTER(DATASETS)\_downloads\sentinel1_grd\`, checksum, extract to a new `data/raw/sentinel1_grd/mc20_2023-01-15/` location.
3. Once Marine credentials exist: request a small, Gulf-of-Mexico-scoped, multi-day CMEMS `uo`/`vo` time series per `docs/datasets/CMEMS_ACQUISITION_READY.md`'s method, region updated to MC20's vicinity.
4. Separately: identify and request a Gulf-of-Mexico-scoped ERA5 subset (new work, not yet specified beyond "domain must include ~28.9N/-89.0W").
5. Only after all four real modalities are on disk: build `data/gold/varuna_event_v0_1/` per Section 18's structure, with a full manifest.
6. Independently of 1–5: the Φ-sensitivity normalization (ADR-0007's open decision) must be ratified before the validity gate can produce anything but a blocking result — this is Track 2's decision, tracked here as a dependency, not owned by this document.

## 25. Definition of REAL_E2E_READY

Not satisfied today, for either candidate, for the reasons in Section 1.
No condition in the task's Section 31 checklist is met end-to-end;
several individual conditions (SAR identity, AIS for MC20, ERA5 for
Ennore) are met in isolation.

## 26. GO / NO-GO

**NO-GO.**

A scientifically honest NO-GO, not a fabricated E2E. The reasons are
enumerable and none of them is "no candidate exists" — a strong one
does (MC20). They are: (1) two independent, unambiguous, unbypassed
credential blockers (Copernicus Marine, Copernicus Data Space) that
apply regardless of region, confirmed by direct authentication tests
this pass, not assumed; (2) a structural validity-gate blocker
(`PHI_DIAGNOSTICS_UNAVAILABLE`) that would prevent any case — real,
synthetic, MC20, Ennore, or otherwise — from reaching `VALID` until a
methodology decision outside this track's scope is ratified.

---

## A. AVAILABLE NOW

- NETRA Gold v0.2, training-ready (independent workstream, unaffected by this document)
- Real MC20-region AIS: 304,960 records, 530 tracks, already extracted from already-downloaded raw data
- Real, catalog-confirmed identity for both candidates' SAR scenes (exact product IDs, exact timestamps, exact size for MC20)
- ERA5 covering Ennore's domain (already on disk, already reconciled)
- Real Φ-sensitivity sweep mechanics (Track 2, ADR-0007) — mechanically real, not yet wired to a gate-usable output

## B. REQUIRED BUT MISSING

- Copernicus Data Space credentials (blocks SAR imagery download for both candidates)
- Copernicus Marine credentials (blocks CMEMS for both candidates)
- Gulf-of-Mexico-scoped ERA5 (MC20 specifically)
- Indian-Ocean AIS source identification (Ennore specifically — a research gap, not a download)
- Φ-sensitivity normalization ratification (Track 2 — blocks the gate regardless of data)
- A live GRD→calibrated-array preprocessing path for a freshly-acquired full scene (neither candidate has this built yet)

## C. NOT REQUIRED FOR FIRST REAL E2E

- OSSD (CHHAYA doesn't need it under the current architecture — unchanged from the prior pass)
- xView3, Bhoonidhi, NISAR, RISAT (future evaluation, not this case)
- Zenodo Part III, ESSD (LOCKED, must never enter this or any training/tuning path)
- ASF's 388GB Level-0 RAW archive (wrong product; MC20's real GRD scene is a separate, correctly-leveled acquisition)
- A unified "all datasets" Gold corpus (explicitly against this task's own Section 28 policy)
