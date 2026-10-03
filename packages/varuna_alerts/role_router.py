from typing import List

# Role-based routing table
ROLE_ROUTING: dict[str, List[str]] = {
    "attribution.generated": ["watch_officer", "district_commander"],
    "validity.evaluated": ["watch_officer"],
    "mission.assigned": ["watch_officer", "pilot", "ops_room"],
    "landfall.predicted": ["district_commander", "pollution_control"],
    "case.completed": ["watch_officer"],
}

def get_recipients(event_type: str) -> List[str]:
    """Threat L-02: Route to correct audience by role."""
    return ROLE_ROUTING.get(event_type, ["watch_officer"])
