"""
Phase 4 / ADR-0015 — the mission FSM is reachable, authorized and audited.

Ten states existed with zero routes: nothing in production could advance a
mission past ASSIGNED, while the frontend already rendered en_route /
on_station / complete badges the system could never produce. And the generic
`MissionService.transition()` had no authorize() call at all — safe only
because it was unrouted.
"""
import pytest
from fastapi.testclient import TestClient

from apps.api.main import app
from varuna_contracts.schemas import AssetTasking, BBox, GeoPoint, SearchBox

client = TestClient(app)

FULL_CHAIN = ["acknowledged", "en_route", "on_station", "searching",
              "contact", "confirmed", "complete"]


def _tok(user: str, pw: str) -> dict:
    r = client.post("/v1/auth/login", json={"username": user, "password": pw})
    assert r.status_code == 200
    return {"Authorization": f"Bearer {r.json()['access_token']}"}


def _officer() -> dict:
    return _tok("officer", "officer-demo-pass")


def _tasking() -> AssetTasking:
    return AssetTasking(
        asset_type="dornier", base_name="INS Test Base",
        search_box=SearchBox(bbox=BBox(min_lon=-89.1, min_lat=28.8,
                                       max_lon=-88.8, max_lat=29.1),
                             center=GeoPoint(lon=-88.97, lat=28.936),
                             area_km2=50.0, phi_mass_contained=0.9),
        pattern="expanding_square", launch_time="2026-01-01T00:00:00Z",
        flight_hours=3.0, probability_of_detection=0.6, rationale="test tasking")


def _new_mission(case_id="CASE-FSM"):
    from apps.api.dependencies import get_mission_service
    return get_mission_service().create_mission(
        case_id=case_id, asset_id="Asset-1", tasking=_tasking())


def _approve(mid: str) -> None:
    r = client.post(f"/v1/missions/{mid}/approve",
                    json={"approved_by": "officer"}, headers=_officer())
    assert r.status_code == 200, r.text


# ------------------------------------------------------------- tasking

def test_tasking_is_persisted_not_discarded():
    """ADR-0015: create_mission accepted an AssetTasking and threw it away,
    so a mission carried only an asset base-name string."""
    m = _new_mission()
    fetched = client.get(f"/v1/missions/{m.mission_id}").json()
    assert fetched["tasking"] is not None
    assert fetched["tasking"]["pattern"] == "expanding_square"
    assert fetched["tasking"]["search_box"]["center"]["lat"] == pytest.approx(28.936)


def test_tasking_survives_a_restart():
    from apps.api.dependencies import get_mission_service
    m = _new_mission()
    from varuna_missions.repository import InMemoryMissionRepository
    path = get_mission_service()._repo._store.path
    reborn = InMemoryMissionRepository(path).get(m.mission_id)
    assert reborn is not None and reborn.tasking is not None
    assert reborn.tasking.pattern == "expanding_square"


# ------------------------------------------------------- the full chain

def test_a_mission_can_now_reach_COMPLETE():
    m = _new_mission()
    _approve(m.mission_id)
    for state in FULL_CHAIN:
        r = client.post(f"/v1/missions/{m.mission_id}/transition",
                        json={"to_state": state, "reason": f"advanced to {state}"},
                        headers=_officer())
        assert r.status_code == 200, f"{state}: {r.text}"
        assert r.json()["state"] == state


def test_legal_transitions_endpoint_reflects_the_real_fsm():
    m = _new_mission()
    before = client.get(f"/v1/missions/{m.mission_id}/transitions").json()
    assert before["state"] == "available"
    assert before["legal_next"] == ["reserved"]
    assert before["terminal"] is False

    _approve(m.mission_id)
    after = client.get(f"/v1/missions/{m.mission_id}/transitions").json()
    assert after["state"] == "assigned"
    assert set(after["legal_next"]) == {"acknowledged", "reassigned"}


def test_terminal_state_offers_nothing_further():
    m = _new_mission()
    _approve(m.mission_id)
    for state in FULL_CHAIN:
        client.post(f"/v1/missions/{m.mission_id}/transition",
                    json={"to_state": state}, headers=_officer())
    client.post(f"/v1/missions/{m.mission_id}/transition",
                json={"to_state": "closed"}, headers=_officer())
    t = client.get(f"/v1/missions/{m.mission_id}/transitions").json()
    assert t["terminal"] is True
    assert t["legal_next"] == []


# ------------------------------------------------------- authorization

def test_unauthenticated_transition_is_401():
    m = _new_mission()
    r = client.post(f"/v1/missions/{m.mission_id}/transition",
                    json={"to_state": "reserved"})
    assert r.status_code == 401


def test_unauthorized_role_is_403_and_state_is_unchanged():
    """The hole ADR-0015 closes: transition() had no authorize() call."""
    m = _new_mission()
    r = client.post(f"/v1/missions/{m.mission_id}/transition",
                    json={"to_state": "reserved"},
                    headers=_tok("analyst", "analyst-demo-pass"))
    assert r.status_code == 403
    assert client.get(f"/v1/missions/{m.mission_id}").json()["state"] == "available"


def test_transitions_are_audited():
    m = _new_mission()
    _approve(m.mission_id)
    client.post(f"/v1/missions/{m.mission_id}/transition",
                json={"to_state": "acknowledged"}, headers=_officer())
    audit = client.get(f"/v1/missions/{m.mission_id}/audit").json()["items"]
    ops = {e["operation"] for e in audit}
    assert "mission.transition.acknowledged" in ops
    assert all(e["subject_id"] == m.mission_id for e in audit)


# --------------------------------------------------------- illegal moves

def test_illegal_edge_is_409_not_500():
    m = _new_mission()
    r = client.post(f"/v1/missions/{m.mission_id}/transition",
                    json={"to_state": "complete"}, headers=_officer())
    assert r.status_code == 409
    assert "illegal mission transition" in r.json()["message"]


def test_unknown_state_name_is_422():
    m = _new_mission()
    r = client.post(f"/v1/missions/{m.mission_id}/transition",
                    json={"to_state": "teleport"}, headers=_officer())
    assert r.status_code == 422


def test_unknown_mission_is_404():
    r = client.post("/v1/missions/MSN-NOPE/transition",
                    json={"to_state": "reserved"}, headers=_officer())
    assert r.status_code == 404


# ---------------------------------------------------------------- cancel

def test_available_mission_cannot_be_cancelled():
    """The locked FSM defines no such edge — refusing is honest rather than
    fabricating a transition."""
    m = _new_mission()
    r = client.post(f"/v1/missions/{m.mission_id}/cancel", headers=_officer())
    assert r.status_code == 409


def test_assigned_mission_can_be_cancelled_to_closed():
    m = _new_mission()
    _approve(m.mission_id)
    r = client.post(f"/v1/missions/{m.mission_id}/cancel",
                    json={"to_state": "closed", "reason": "weather"},
                    headers=_officer())
    assert r.status_code == 200
    assert r.json()["state"] == "closed"


# --------------------------------------------------------------- history

def test_history_records_why_not_just_when():
    m = _new_mission()
    _approve(m.mission_id)
    client.post(f"/v1/missions/{m.mission_id}/transition",
                json={"to_state": "acknowledged", "reason": "crew confirmed receipt"},
                headers=_officer())
    h = client.get(f"/v1/missions/{m.mission_id}/history").json()
    assert h["current_state"] == "acknowledged"
    assert h["human_approved_by"] == "officer"
    ack = [e for e in h["history"] if e["state"] == "acknowledged"]
    assert ack and ack[0]["reason"] == "crew confirmed receipt"


def test_case_scoped_mission_listing():
    m = _new_mission(case_id="CASE-SCOPED")
    items = client.get("/v1/cases/CASE-SCOPED/missions").json()["items"]
    assert [i["mission_id"] for i in items] == [m.mission_id]
