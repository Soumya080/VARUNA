# VARUNA GRID v2 - Data Directory Convention

This directory follows the medallion architecture convention for the data pipeline (M6):

* **`raw/`**: Unmodified source artifacts directly from Zenodo, Sentinel Hub, etc.
* **`bronze/`**: Unzipped, basic format converted artifacts, unvalidated.
* **`silver/`**: Validated, canonicalized, deduplicated, split, and tiled data (TileRecords).
* **`gold/`**: Fully normalized, ML-ready tensors grouped by dataset splits.
* **`manifests/`**: Output manifests detailing data lineage and splits.
