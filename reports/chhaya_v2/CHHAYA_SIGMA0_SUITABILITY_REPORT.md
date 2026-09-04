# CHHAYA sigma0 suitability report

Peak-signal-above-mean (in sigma units) per tile per product, and whether
CA-CFAR is physically CAPABLE of firing at each threshold. This measures
capability, not detection — a tile that clears the threshold may still
genuinely contain zero vessels.

| Product | Tile | Peak sigma above mean | Fires @4σ | @6σ | @8σ | @15σ | @30σ |
|---|---|---|---|---|---|---|---|
| netra_normalized (existing) | mc20_2023-01-15__r0c0 | 10.22 | YES | YES | YES | no | no |
| netra_normalized (existing) | mc20_2023-01-15__r0c512 | 3.41 | no | no | no | no | no |
| netra_normalized (existing) | mc20_2023-01-15__r0c1024 | 10.87 | YES | YES | YES | no | no |
| netra_normalized (existing) | mc20_2023-01-15__r512c0 | 3.45 | no | no | no | no | no |
| netra_normalized (existing) | mc20_2023-01-15__r512c512 | 3.76 | no | no | no | no | no |
| netra_normalized (existing) | mc20_2023-01-15__r512c1024 | 3.81 | no | no | no | no | no |
| netra_normalized (existing) | mc20_2023-01-15__r1024c0 | 3.43 | no | no | no | no | no |
| netra_normalized (existing) | mc20_2023-01-15__r1024c512 | 9.82 | YES | YES | YES | no | no |
| netra_normalized (existing) | mc20_2023-01-15__r1024c1024 | 9.97 | YES | YES | YES | no | no |
| sigma0 (Phase 5A, new) | mc20_2023-01-15__r0c0 | 140.34 | YES | YES | YES | YES | YES |
| sigma0 (Phase 5A, new) | mc20_2023-01-15__r0c512 | 7.26 | YES | YES | no | no | no |
| sigma0 (Phase 5A, new) | mc20_2023-01-15__r0c1024 | 156.54 | YES | YES | YES | YES | YES |
| sigma0 (Phase 5A, new) | mc20_2023-01-15__r512c0 | 7.67 | YES | YES | no | no | no |
| sigma0 (Phase 5A, new) | mc20_2023-01-15__r512c512 | 8.93 | YES | YES | YES | no | no |
| sigma0 (Phase 5A, new) | mc20_2023-01-15__r512c1024 | 8.91 | YES | YES | YES | no | no |
| sigma0 (Phase 5A, new) | mc20_2023-01-15__r1024c0 | 7.60 | YES | YES | no | no | no |
| sigma0 (Phase 5A, new) | mc20_2023-01-15__r1024c512 | 152.42 | YES | YES | YES | YES | YES |
| sigma0 (Phase 5A, new) | mc20_2023-01-15__r1024c1024 | 127.85 | YES | YES | YES | YES | YES |
