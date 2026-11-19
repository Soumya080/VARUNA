import pytest
from pathlib import Path
from varuna_data_eng.varuna_source_adapters.zenodo_part2_adapter import ZenodoPart2Adapter

def test_zenodo_part2_adapter_discovery(tmp_path):
    # Mock extracted directory structure
    lookalike_dir = tmp_path / "Lookalike" / "Lookalike"
    lookalike_mask = tmp_path / "Lookalike" / "Mask_lookalike"
    no_oil_dir = tmp_path / "No_Oil" / "No_oil"
    no_oil_mask = tmp_path / "No_Oil" / "Mask_no_oil"
    
    for d in [lookalike_dir, lookalike_mask, no_oil_dir, no_oil_mask]:
        d.mkdir(parents=True, exist_ok=True)
        
    # Create fake tiffs
    (lookalike_dir / "001.tif").write_bytes(b"fake_image")
    (lookalike_mask / "001.tif").write_bytes(b"fake_mask")
    (no_oil_dir / "002.tif").write_bytes(b"fake_image")
    (no_oil_mask / "002.tif").write_bytes(b"fake_mask")
    
    # Initialize adapter
    adapter = ZenodoPart2Adapter(str(tmp_path))
    
    # We must patch rasterio because it will fail to read "fake_image"
    import rasterio
    class DummySrc:
        width = 2048
        height = 2048
        res = (10.0, 10.0)
        class Bounds:
            left, bottom, right, top = 0.0, 0.0, 10.0, 10.0
        bounds = Bounds()
        def __enter__(self): return self
        def __exit__(self, *args): pass
        
    original_open = rasterio.open
    rasterio.open = lambda *args, **kwargs: DummySrc()
    
    try:
        sar_list, mask_list = adapter.discover()
        assert len(sar_list) == 2
        assert len(mask_list) == 2
        
        # Verify categorizations
        cats = {sar.metadata["original_category"] for sar in sar_list}
        assert "Lookalike" in cats
        assert "No_Oil" in cats
    finally:
        rasterio.open = original_open
