"""Phase 2a — message-precedence vocabulary (FLASH/IMMEDIATE/PRIORITY/ROUTINE)
and the formal PRECEDENCE/FROM/TO/SUBJECT/SITUATION/ACTION REQUIRED/
ACKNOWLEDGE message-block structure. No send-logic change is tested here —
templates.py has none; this is purely rendering."""
from varuna_alerts.templates import (
    SMS_MAX_CHARS, precedence_for, render_sms, render_subject, render_text,
)

BASE_ALERT = {
    "alert_id": "ALT-1", "case_id": "CASE-9", "severity": "critical",
    "event_type": "landfall.predicted", "material_dimension": "landfall.prediction",
    "reason": "forecast predicts landfall at Replay coastal segment",
    "severity_basis": "a landfall is predicted while the validity gate blocks action",
    "engine_mode": "real", "is_simulated": False,
    "created_at": "2026-09-03T10:00:00Z", "evidence_refs": ["forecast-CASE-9"],
    "previous_value": 0, "current_value": 1,
    "routing": {"recipients": [{"role": "duty_officer"}, {"role": "supervisor"}]},
}


def test_precedence_mapping_matches_severity_scale():
    assert precedence_for("critical") == "FLASH"
    assert precedence_for("high") == "IMMEDIATE"
    assert precedence_for("medium") == "PRIORITY"
    assert precedence_for("warning") == "PRIORITY"
    assert precedence_for("low") == "ROUTINE"
    assert precedence_for("info") == "ROUTINE"


def test_precedence_is_case_insensitive_and_handles_enum_like_objects():
    class FakeEnum:
        value = "CRITICAL"
    assert precedence_for(FakeEnum()) == "FLASH"
    assert precedence_for("CRITICAL") == "FLASH"


def test_unknown_severity_falls_back_to_routine_not_a_crash():
    assert precedence_for("nonsense") == "ROUTINE"
    assert precedence_for(None) == "ROUTINE"


def test_subject_leads_with_precedence():
    subj = render_subject({**BASE_ALERT, "severity": "critical"})
    assert subj.startswith("FLASH —")


def test_sms_leads_with_precedence_and_stays_bounded():
    sms = render_sms({**BASE_ALERT, "severity": "high"})
    assert sms.startswith("IMMEDIATE ")
    assert len(sms) <= SMS_MAX_CHARS


def test_text_carries_the_formal_message_block_structure():
    out = render_text(BASE_ALERT)
    for field in ("PRECEDENCE:", "FROM:", "TO:", "SUBJECT:", "SITUATION",
                  "ACTION REQUIRED", "ACKNOWLEDGE"):
        assert field in out
    assert "FLASH" in out
    assert "duty_officer, supervisor" in out


def test_text_uses_fallback_recipient_line_when_routing_is_empty():
    out = render_text({**BASE_ALERT, "routing": {}})
    assert "Duty Officer (default)" in out
