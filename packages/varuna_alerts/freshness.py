from datetime import datetime, timezone
from typing import Tuple

def check_freshness(event_timestamp: datetime, max_age_seconds: int = 3600
                    ) -> Tuple[bool, str]:
    """Threat L-03: Suppress expired alerts."""
    age = (datetime.now(timezone.utc) - event_timestamp).total_seconds()
    if age > max_age_seconds:
        return False, f"Alert expired (age={age:.0f}s > {max_age_seconds}s)"
    return True, "fresh"
