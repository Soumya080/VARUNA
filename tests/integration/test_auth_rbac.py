import pytest
from varuna_infra.rbac import has_permission, Permission
from varuna_infra.auth_models import User
from datetime import datetime

def test_auth_rbac_integration():
    user = User(user_id="u1", username="admin", password_hash="hash", role="admin", is_active=True, created_at=datetime.now())
    
    assert has_permission(user.role, Permission.APPROVE_MODEL)
    assert has_permission(user.role, Permission.CREATE_CASE)
