from datetime import datetime, timezone
from typing import Dict

class DedupeWindow:
    """Threat L-05: Idempotency-key dedup within time window."""

    def __init__(self, window_seconds: int = 300):
        self._window = window_seconds
        self._seen: Dict[str, datetime] = {}

    def is_duplicate(self, key: str) -> bool:
        now = datetime.now(timezone.utc)
        # Clean expired entries
        self._seen = {k: t for k, t in self._seen.items()
                      if (now - t).total_seconds() < self._window}
        if key in self._seen:
            return True
        self._seen[key] = now
        return False
