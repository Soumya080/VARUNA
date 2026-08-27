import json
from pathlib import Path
from typing import Optional, Dict, Any

class DemoModeConfig:
    """DEMO_MODE support. When enabled, all providers return frozen fixtures."""

    def __init__(self, enabled: bool = False, fixture_dir: str = "tests/fixtures"):
        self.enabled = enabled
        self.fixture_dir = Path(fixture_dir)

    def get_frozen_case(self, case_id: str) -> Optional[Dict[str, Any]]:
        """Return pre-computed case result from fixture, or None."""
        if not self.enabled:
            return None
            
        fixture_path = self.fixture_dir / f"{case_id}.json"
        if fixture_path.exists():
            try:
                with open(fixture_path, "r") as f:
                    return json.load(f)
            except Exception:
                return None
        return None
