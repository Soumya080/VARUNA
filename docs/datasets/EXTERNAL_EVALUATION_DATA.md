# External Evaluation Data — Locked & Future

**Status:** Neither dataset below is present locally (confirmed via
`data/catalog/dataset_inventory.json`, both `status: missing`). Neither is
downloaded by this pass — both require an explicit, deliberate acquisition
decision, and both must be stored and used under the constraints below
once acquired.

## LOCKED_EVALUATION — Zenodo Part III

**Source:** the same Zenodo record as Parts I/II (multi-part release);
Part III is the held-out test split the dataset's authors define.
**Expected format:** GeoTIFF pairs, same structure as Part I (2048×2048,
VV/VH float32, EPSG:4326) based on the shared dataset documentation.
**Expected size:** unconfirmed — proportional to Parts I/II (51–92GB each);
budget similarly.
**Not downloaded here** — source identity needs confirming against the
exact Zenodo record ID used for Parts I/II before acquisition, to avoid
downloading a mismatched or superseded version.

## LOCKED_EVALUATION — ESSD 2025 Eastern Mediterranean oil spill dataset

**Source:** ESSD (Earth System Science Data) 2025 publication, external to
Zenodo. **Expected content:** dual-interpreter labels, ~2,290 look-alike
patches (per earlier audit citation of the published dataset description).
**Not downloaded here** — requires locating the specific ESSD DOI/publication
and its data availability statement first.

## LOCKED_EVALUATION constraint (applies to both, once acquired)

Per instruction, both datasets **must never be used for**:

- training
- hyperparameter tuning
- threshold tuning
- normalization statistic computation
- early stopping

They exist solely to produce a final, one-time generalization measurement
after a model is otherwise finished. Storage plan once acquired: a
separate top-level path (e.g. `data/raw/zenodo_part3_LOCKED/`,
`data/raw/essd_LOCKED/`) with the `_LOCKED` suffix as a naming-convention
guard against accidental inclusion in a training glob, plus a
`data/catalog/locked_evaluation_manifest.json` recording exactly which
runs (if any) have touched them and confirming none did until the
designated final-evaluation step.

## FUTURE_EVALUATION — Bhoonidhi / NISAR / RISAT

All three: `status: missing`, `.gitkeep` only. Not required for the first
real end-to-end case (which targets the Gulf-of-Mexico anchor case,
Zenodo Part I imagery + Gulf AIS + Arabian-Sea-domain ERA5/CMEMS
forcing — none of these three are on that path).

| Dataset | Provider | Recommendation |
|---|---|---|
| Bhoonidhi | ISRO | Acquire only once an Indian-waters deployment evaluation is explicitly scheduled — see the ASF Level-0 → GRD gap (Priority 4 in this workstream's brief), which would need resolving first anyway. |
| NISAR | NASA/ISRO | Mission data volume/availability should be re-checked at acquisition time — flagged FUTURE, not started. |
| RISAT | ISRO | Same as Bhoonidhi — bundle into one Indian-domain cross-sensor acquisition phase rather than acquiring separately. |

No action taken this pass beyond this recommendation, per the "do not
download large cross-sensor datasets in this milestone unless required for
the first real study case" instruction.
