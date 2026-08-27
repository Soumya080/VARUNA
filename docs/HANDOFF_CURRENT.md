PROJECT:
VARUNA GRID v2

CURRENT MILESTONE:
Lab Training Readiness / M6.5 freeze

BRANCH:
milestone/m3.5-productization

FREEZE COMMIT:
bf9076c

VERIFIED:
- repository tests
- M6 data pipeline synthetic execution
- DataGuard
- dedup
- leakage
- split
- tiling
- normalization
- NETRA smoke
- CHHAYA smoke
- lab bootstrap

NOT VERIFIED:
- real Sentinel-1 ingestion
- real oil-spill preprocessing
- real xView3 ingestion
- real AIS ingestion
- real ERA5 ingestion
- real CMEMS ingestion
- full GOLD dataset generation from real data
- real NETRA performance
- real CHHAYA performance
- M2.2 scientific validation

SCIENTIFIC STATUS:
EXPERIMENTAL / UNVALIDATED

LAB NEXT STEPS:
1. clone
2. uv sync
3. bootstrap
4. GPU check
5. smoke test
6. place data
7. validate
8. canonicalize
9. build GOLD
10. train
