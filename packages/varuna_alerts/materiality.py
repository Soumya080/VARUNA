from typing import Tuple, Optional
from varuna_contracts.evidence import ValidityState

def check_materiality(gate_state: Optional[ValidityState],
                      event_type: str) -> Tuple[bool, str]:
    """Threat L-01: Block alerts on unverified/restricted cases.

    Returns:
        (should_send, reason)
    """
    if gate_state is None:
        return False, "No validity gate result available"

    if not gate_state.allows_operational_action:
        return False, f"Gate state={gate_state.value} - alert withheld"

    # Only material events trigger external alerts
    material_events = {"attribution.generated", "validity.evaluated",
                       "mission.assigned", "landfall.predicted"}
    if event_type not in material_events:
        return False, f"Event {event_type} is not material for external alerting"

    return True, "material"
