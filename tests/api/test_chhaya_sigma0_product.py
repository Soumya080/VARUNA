"""Phase 5A regression lock (docs/product/HONESTY_LEDGER.md #13-14).

Two things this locks:
  1. M11 — the router used to index `arr[0]` as VH; it was actually VV
     (`apply_netra_normalization`'s real return order). Now indexed by
     `channel_order`, never bare position.
  2. Phase 5A's actual success criterion: the `sigma0` product (raw
     calibrated dB, built by `scripts/build_mc20_chhaya_sigma0.py`) makes
     CA-CFAR physically CAPABLE of firing, which the normalized product's
     [0,1] clipping structurally prevented for most of these tiles.

Skipped automatically when the sigma0 product hasn't been built on disk —
this test verifies real behavior against real data, it does not fabricate
a fixture to run against.
"""
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from apps.api.main import app

client = TestClient(app)

_SIGMA0_RECORDS = (
    Path(__file__).resolve().parents[2]
    / "data" / "gold" / "events" / "mc20_v0_1_sigma0" / "sar" / "tile_records.json"
)

pytestmark = pytest.mark.skipif(
    not _SIGMA0_RECORDS.exists(),
    reason="mc20_v0_1_sigma0 not built — run scripts/build_mc20_chhaya_sigma0.py",
)


def _sigma0_tiles():
    r = client.get("/v1/chhaya/tiles?product=sigma0")
    assert r.status_code == 200
    body = r.json()
    assert body["available"], body.get("reason")
    return body["tiles"]


def test_sigma0_tiles_are_listed_separately_from_netra_normalized():
    sigma0 = _sigma0_tiles()
    normalized = client.get("/v1/chhaya/tiles?product=netra_normalized").json()["tiles"]
    assert len(sigma0) == len(normalized) == 9, (
        "sigma0 and netra_normalized should tile the same real scene identically"
    )


def test_cfar_is_physically_capable_of_firing_on_sigma0():
    """The actual Phase 5A success criterion: CFAR must be CAPABLE of
    firing on at least one real tile now — not that it necessarily finds a
    vessel on every tile (a truthful zero on some tiles is a valid
    outcome, per build_mc20_chhaya_sigma0.py's own module docstring)."""
    any_suitable = False
    for t in _sigma0_tiles():
        r = client.get(f"/v1/chhaya/investigate/{t['tile_id']}?product=sigma0")
        assert r.status_code == 200
        suitability = r.json()["_input"].get("suitability")
        if suitability and suitability.get("suitable_for_cfar"):
            any_suitable = True
    assert any_suitable, (
        "no sigma0 tile reports suitable_for_cfar=true — Phase 5A's physical-capability "
        "criterion has regressed"
    )


def test_channel_indexing_is_explicit_not_positional():
    """M11's regression lock: every sigma0 tile record must carry an
    explicit channel_order naming VH — a router that fell back to
    `arr[0]` again would silently feed VV into CFAR."""
    import json
    records = json.loads(_SIGMA0_RECORDS.read_text(encoding="utf-8"))
    assert records, "no sigma0 tile records to check"
    for rec in records:
        order = rec.get("channel_order")
        assert order, f"{rec['tile_id']} has no channel_order — M11 could regress silently"
        assert any("VH" in ch for ch in order), order
        assert any("VV" in ch for ch in order), order
