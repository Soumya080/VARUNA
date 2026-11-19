import pytest
from datetime import datetime, timezone, timedelta

from varuna_contracts.evidence import ValidityState, EvidenceEnvelope, TrustState, QualityMetrics
from varuna_alerts.materiality import check_materiality
from varuna_alerts.role_router import get_recipients
from varuna_alerts.freshness import check_freshness
from varuna_alerts.dedupe import DedupeWindow
from varuna_alerts.channels.mock_sms import MockSmsChannel

def test_alert_materiality_blocks_unverified():
    # Threat L-01
    gate_state = ValidityState.RESTRICTED
    should, _ = check_materiality(gate_state, "attribution.generated")
    assert should is False

def test_alert_routing_correct_audience():
    # Threat L-02
    recipients = get_recipients("mission.assigned")
    assert "pilot" in recipients
    assert "pollution_control" not in recipients

def test_alert_freshness_suppresses_old():
    # Threat L-03
    old_time = datetime.now(timezone.utc) - timedelta(hours=2)
    fresh, _ = check_freshness(old_time, max_age_seconds=3600)
    assert fresh is False

def test_alert_provider_labelling():
    # Threat L-04
    ch = MockSmsChannel()
    result = ch.send("officer", "test", "body")
    assert result.is_simulated is True

def test_alert_dedupe():
    # Threat L-05
    dd = DedupeWindow(window_seconds=300)
    assert dd.is_duplicate("key1") is False
    assert dd.is_duplicate("key1") is True   # second call within window
