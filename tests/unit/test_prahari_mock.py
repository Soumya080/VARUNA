import pytest
from varuna_contracts.schemas import BBox
from varuna_domain.prahari.mock import MockPrahariProvider

def test_prahari_mock_watch():
    provider = MockPrahariProvider()
    scenes = []
    
    def on_scene(path: str):
        scenes.append(path)
        if len(scenes) == 2:
            provider.stop()
            
    provider.watch(BBox(min_lon=70, min_lat=10, max_lon=71, max_lat=11), on_scene)
    
    # In Mock, watch just calls replay synchronously with fixture scenes
    assert len(scenes) == 2
    assert "scene_mock_01.tif" in scenes[0]
