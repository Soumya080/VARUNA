# M2 SCIENTIFIC AUDIT

## Verdict
**FAIL** 

The reported 20% accuracy is a statistical artifact caused by a severe mathematical flaw in the posterior normalization. The model trivially predicts `LATENT_SOURCE` for all 50 cases. Furthermore, the experiment harness contains critical scientific leakage (true age and true origin are leaked to the inference engine) and the "monotonic degradation with age" is an illusion caused by a deterministic age-seed mapping.

## Provenance Audit
- **Exact Commit**: The manifest records `e8a6186335f1f4b1ed3350d64b60661a3677d2f8`, but the actual M2 freeze commit is `0888874`. This discrepancy occurred because the manifest was generated prior to the final freeze commit.
- **Experiment Code/Config Version**: v2
- **Seed**: `42 + i` (per case)
- **Result Generation Timestamp**: Matches manifest.

## Candidate Generation Audit
| Case Type | Candidate Count | Truth Type | Truth Visible | Generation Method |
| :--- | :--- | :--- | :--- | :--- |
| Known Source (40) | 5 (1 truth + 4 decoys) | `123456789` | Yes | Decoys placed precisely around true release origin (`rng.normal(release_lon, 0.1)`) |
| Latent Source (10) | 4 (4 decoys) | `LATENT_SOURCE` | No | Decoys placed precisely around true release origin (`rng.normal(release_lon, 0.1)`) |

*Finding*: Candidate counts are unbalanced between classes (5 vs 4). More critically, candidate generation suffers from **severe spatial leakage**: decoys are spawned precisely around the *true release location* rather than drawn uniformly from the operational region. 

## Baseline Audit
Only `naive_distance_baseline` is used in the evaluation harness. The reported 16% accuracy is purely an artifact of random chance on the known cases: 
- For known sources (40 cases), the baseline guesses among 5 candidates (expected 1/5 = 20%). It correctly guessed 8 cases (8/40 = 20%). 
- For latent sources (10 cases), the baseline incorrectly picked a decoy because it only predicts latent if all candidates are >100km away (which rarely happens since decoys are spawned at the true origin). 
- Overall: 8/50 = 16%.

## Latent Source Audit
The model predicted `LATENT_SOURCE` for all 50 cases because of a **massive dimensionality mismatch** in the posterior calculation:
1. `L_k` (Candidate Likelihood) is computed as a 1D path integral (`Σ_i Φ[t_i, y_i, x_i] · Δt_i`). Since `Φ` is a volume-normalized 3D probability density, summing a few points along a track yields a tiny number (e.g., `1e-4`).
2. `L_0` (Latent Probability) is computed as a 3D volume integral (`1 - Σ Φ[corridors]`). Since tracks only intersect a tiny fraction of the total 3D space, `L_0` evaluates to ~`0.999`.
3. In `posterior.py`, these are summed (`total = sum(L_k) + L_0`). 
Result: `LATENT_SOURCE` gets a posterior of `0.999 / 1.0 ≈ 99.9%`, trivially dominating every single case.

## Accuracy Metric Audit
The reported `overall_accuracy = 0.20` is calculated over all 50 cases by checking `pred_mmsi == true_mmsi`. 
Because the model unconditionally predicts `LATENT_SOURCE`, it gets 0/40 known cases right and 10/10 latent cases right. 
10/50 = 20%. The model has effectively zero attribution capability; it is a broken clock that is right 20% of the time because 20% of the test set is latent.

## Age Monotonicity Audit
The claim that accuracy degrades monotonically with age is **false**.
The 10 latent cases were assigned the first 10 seeds (42 to 51). The age formula is deterministic: `12.0 + (seed % 60)`. 
Thus, the 10 latent cases strictly received ages 54 through 63. Since *only* latent cases were marked correct, the model scored 100% accuracy for ages 54–63 and 0% accuracy everywhere else. This is a block artifact, not monotonic degradation.

## Scientific Leakage Audit
| Component | Classification | Reason |
| :--- | :--- | :--- |
| Truth Coordinate | PASS | Slick is forward-advected properly. |
| Truth Time | PASS | |
| Truth Age | **FAIL** | `sweep.py` passes `backward_duration_hours=true_age_hours` directly into `PratiConfig`, giving the inference engine perfect knowledge of the exact slick age. |
| Candidate Gen | **FAIL** | Decoys are generated within 0.1 degrees of the *true unobserved release point*, giving the search algorithm perfect spatial priors. |
| Forcing / Search | PASS | Synthetic models use different implementations (Truth vs Model). |
| Latent Labels | PASS | |

## Critical Problems
1. **Dimensionality Mismatch in Posterior**: `L_0` (Volume) vs `L_k` (Line Integral).
2. **Spurious 20% Accuracy**: Caused purely by the model unconditionally predicting LATENT_SOURCE.
3. **Age Leakage**: True age is passed directly to the inference engine.
4. **Spatial Leakage**: Candidates are spawned exactly at the true release point.
5. **Age Spikes**: Deterministic seed math groups all latent cases into a narrow age band (54-63h).

## Required Fixes
1. **Fix Posterior Normalization**: Standardize the units between `L_k` and `L_0` (e.g., assign a physical corridor volume to the path integral so both are volume integrals, or evaluate latent probability as a marginal over empty space).
2. **Remove Leakage**: Fix `sweep.py` to use a broad age prior independent of `true_age_hours`, and distribute candidates uniformly across the bounding box.
3. **Randomize Ages**: Shuffle true ages so latent cases are distributed evenly.
4. **Balance Classes**: Ensure baseline candidate sets are equal in size.
5. **Update Manifest**: Point manifest to correct freeze commit.

## M3 Readiness
**NOT READY.** M3 cannot proceed until the posterior math is fixed, the leakage is removed, and the baseline evaluation is made fair.
