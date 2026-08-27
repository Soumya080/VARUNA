import pytest
from varuna_infra.rbac import has_permission, Role, Permission

def test_rbac_admin():
    assert has_permission("admin", Permission.CREATE_CASE)
    assert has_permission("admin", Permission.APPROVE_MODEL)
    
def test_rbac_duty_officer():
    assert has_permission("duty_officer", Permission.APPROVE_MISSION)
    assert not has_permission("duty_officer", Permission.APPROVE_MODEL)
    
def test_rbac_invalid_role():
    assert not has_permission("hacker", Permission.VIEW_CASE)
