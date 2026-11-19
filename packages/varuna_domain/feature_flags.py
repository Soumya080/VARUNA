from typing import Dict, Optional

class FeatureFlags:
    """Simple config-driven feature flags. No external service."""

    def __init__(self, overrides: Optional[Dict[str, bool]] = None):
        self._defaults = {
            "netra_enabled": True,
            "chhaya_enabled": True,
            "pravaah_enabled": True,
            "abhiyan_enabled": True,
            "alerts_enabled": True,
            "smriti_enabled": True,
            "prahari_enabled": False,  # opt-in for persistent watch
            "demo_mode": False,
        }
        self._overrides = overrides or {}

    def is_enabled(self, flag: str) -> bool:
        return self._overrides.get(flag, self._defaults.get(flag, False))
