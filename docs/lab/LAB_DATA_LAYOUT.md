# VARUNA GRID v2 — Laboratory Data Layout & Directory Conventions

VARUNA adopts a strict **Medallion Data Architecture** (Raw -> Bronze -> Silver -> Gold) to ensure strict data lineage, auditability, reproducible cross-validation splits, and prevention of data leakage.

---

## 1. Directory Tree Hierarchy

```
data/
├── raw/                      # Raw, immutable source files (Read-Only)
│   ├── sentinel1/            # Sentinel-1 Level-1 GRD SAFE / GeoTIFF scenes
│   ├── zenodo/               # Zenodo Marine Oil Spill Benchmark archives (.zip, .tif)
│   ├── essd/                 # ESSD Global Oil Slick Dataset
│   ├── xview3/               # xView3 Dark Vessel & Slick SAR challenge data
│   ├── ais/                  # Terrestrial & Satellite AIS CSV / NMEA logs
│   ├── era5/                 # ECMWF ERA5 NetCDF / GRIB surface wind fields
│   ├── cmems/                # Copernicus Marine Ocean Current velocity NetCDFs
│   ├── bhoonidhi/            # ISRO Bhoonidhi Satellite imagery
│   ├── nisar/                # NASA-ISRO SAR Data
│   └── risat/                # ISRO RISAT-1 / 1A SAR Data
│
├── bronze/                   # Unpacked & indexed source files
│   └── (unzipped rasters, normalized file encodings)
│
├── silver/                   # Validated, deduplicated canonical schemas
│   ├── *.npy                 # Canonical float32 SAR rasters (VV, VH)
│   ├── mask_*.npy            # Labeled pixel masks (0=bg, 1=oil, 2=lookalike)
│   └── sar_*_meta.json       # Canonical metadata headers (CanonicalSAR)
│
├── gold/                     # Tiled, normalized, leak-free ML tensors
│   ├── netra/                # Spatial tiles (3, 512, 512) for NETRA U-Net training
│   ├── chhaya/               # Fixed-length trajectory tensors for CHHAYA LSTM
│   └── attribution/          # Golden multi-modal case benchmark packs
│
└── manifests/                # Lineage & frozen split assignments
    └── gold_v1.0.0_manifest.json
```

---

## 2. Layer Descriptions & Ingestion Rules

### 1. `data/raw/` (Bronze Stage Input)
- **Immutable**: Raw files are never modified in-place by any pipeline script.
- **Gitignored**: Large rasters and CSVs must never be checked into Git.
- **Safety**: If files are missing, the bootstrap reports `NOT PROVIDED` without breaking execution.

### 2. `data/silver/` (Canonical Tier)
- **Validation**: Every scene must clear `QualityEngine` and `DataGuardV2`.
- **Deduplication**: Hash and spatial deduplication removes duplicate overlapping swaths.
- **Schemas**: Standardized to `CanonicalSAR`, `OilMask`, `RawAISTrack`, and `ForcingCube`.

### 3. `data/gold/` (Training Ready)
- **Splits**: Strict geographic-temporal partitions (Train / Val / Test).
- **Leakage Guard**: Mathematical verification that no scene or region overlaps between splits.
- **Normalization**: Zero-mean, unit-variance normalization computed **exclusively from the Train split**.
- **Tiling**: Extracted into uniform spatial tiles (e.g. 512x512) with spatial overlap metadata.

---

## 3. Dataset Placement Guidelines for Lab Users

When copying datasets from external drives or university storage:

| Dataset | Destination Folder | Expected Format |
| :--- | :--- | :--- |
| **Sentinel-1 SAR** | `data/raw/sentinel1/` | `.zip`, `.SAFE` folders, or `.tif` GRD images |
| **Zenodo Oil Spills**| `data/raw/zenodo/` | Extracted images and ground truth masks |
| **Historical AIS** | `data/raw/ais/` | `.csv` or `.parquet` (Columns: `mmsi, timestamp, lon, lat, sog, cog, heading`) |
| **ERA5 Wind** | `data/raw/era5/` | `.nc` (Variables: `u10`, `v10`, `time`, `latitude`, `longitude`) |
| **CMEMS Currents** | `data/raw/cmems/` | `.nc` (Variables: `uo`, `vo`, `time`, `depth`, `latitude`, `longitude`) |

---

## 4. Pipeline Execution Commands

```bash
# 1. Check data integrity
python scripts/validate_data.py

# 2. Canonicalize raw data to Silver
python scripts/build_canonical.py

# 3. Create Manifest and calculate splits
python scripts/build_manifest.py

# 4. Generate Gold tensors
python scripts/build_gold.py
```
