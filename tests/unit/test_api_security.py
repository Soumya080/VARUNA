"""
VARUNA GRID — apps.api.security tests (Phase 5, VARUNA_PRODUCT_READY hardening).

Covers the identity-resolution boundary itself: real signed-JWT verification,
rejection of an unsigned or wrong-secret token, and the demo_mode gate on the
unsigned header path. Router-level "does authorization actually block the
request" tests live in tests/api/test_cases.py and
tests/unit/test_authorization_enforcement.py; this file is about
get_principal() in isolation.
"""
from datetime import timedelta

import pytest
from fastapi import HTTPException

from apps.api.config import settings
from apps.api.security import get_principal
from varuna_infra.auth import create_access_token


def test_valid_jwt_resolves_principal():
    token = create_access_token(
        user_id="alice", role="duty_officer",
        secret_key=settings.jwt_secret_key, expires_delta=timedelta(minutes=5),
    )
    principal = get_principal(authorization=f"Bearer {token}", x_user_id=None, x_user_role=None)
    assert principal.principal_id == "alice"
    assert principal.role == "duty_officer"


def test_jwt_signed_with_wrong_secret_is_rejected():
    token = create_access_token(
        user_id="mallory", role="admin",
        secret_key="not-the-real-secret", expires_delta=timedelta(minutes=5),
    )
    with pytest.raises(HTTPException) as exc_info:
        get_principal(authorization=f"Bearer {token}", x_user_id=None, x_user_role=None)
    assert exc_info.value.status_code == 401


def test_expired_jwt_is_rejected():
    token = create_access_token(
        user_id="alice", role="duty_officer",
        secret_key=settings.jwt_secret_key, expires_delta=timedelta(seconds=-1),
    )
    with pytest.raises(HTTPException) as exc_info:
        get_principal(authorization=f"Bearer {token}", x_user_id=None, x_user_role=None)
    assert exc_info.value.status_code == 401


def test_malformed_authorization_header_is_rejected():
    with pytest.raises(HTTPException) as exc_info:
        get_principal(authorization="NotBearer sometoken", x_user_id=None, x_user_role=None)
    assert exc_info.value.status_code == 401


def test_no_credentials_is_rejected():
    with pytest.raises(HTTPException) as exc_info:
        get_principal(authorization=None, x_user_id=None, x_user_role=None)
    assert exc_info.value.status_code == 401


def test_header_identity_rejected_outside_demo_mode(monkeypatch):
    monkeypatch.setattr(settings, "demo_mode", False)
    with pytest.raises(HTTPException) as exc_info:
        get_principal(authorization=None, x_user_id="bob", x_user_role="admin")
    assert exc_info.value.status_code == 401


def test_header_identity_accepted_in_demo_mode(monkeypatch):
    monkeypatch.setattr(settings, "demo_mode", True)
    principal = get_principal(authorization=None, x_user_id="bob", x_user_role="admin")
    assert principal.principal_id == "bob"
    assert principal.role == "admin"
