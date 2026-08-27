from enum import StrEnum
from typing import Set

class Role(StrEnum):
    ADMIN = "admin"
    DUTY_OFFICER = "duty_officer"
    ANALYST = "analyst"
    FIELD_OPERATOR = "field_operator"
    READ_ONLY = "read_only"
    SYSTEM = "system"

class Permission(StrEnum):
    CREATE_CASE = "create_case"
    APPROVE_MISSION = "approve_mission"
    VIEW_CASE = "view_case"
    VIEW_SENSITIVE = "view_sensitive"
    MODIFY_CONFIG = "modify_config"
    MANAGE_USERS = "manage_users"
    SUBMIT_OUTCOME = "submit_outcome"
    APPROVE_MODEL = "approve_model"
    VIEW_DASHBOARD = "view_dashboard"
    TRIGGER_ALERT = "trigger_alert"

ROLE_PERMISSIONS: dict[Role, Set[Permission]] = {
    Role.ADMIN: {
        Permission.CREATE_CASE, Permission.APPROVE_MISSION, Permission.VIEW_CASE,
        Permission.VIEW_SENSITIVE, Permission.MODIFY_CONFIG, Permission.MANAGE_USERS,
        Permission.SUBMIT_OUTCOME, Permission.APPROVE_MODEL, Permission.VIEW_DASHBOARD,
        Permission.TRIGGER_ALERT
    },
    Role.DUTY_OFFICER: {
        Permission.CREATE_CASE, Permission.APPROVE_MISSION, Permission.VIEW_CASE,
        Permission.VIEW_SENSITIVE, Permission.SUBMIT_OUTCOME, Permission.VIEW_DASHBOARD,
        Permission.TRIGGER_ALERT
    },
    Role.ANALYST: {
        Permission.VIEW_CASE, Permission.VIEW_SENSITIVE, Permission.VIEW_DASHBOARD
    },
    Role.FIELD_OPERATOR: {
        Permission.VIEW_CASE, Permission.SUBMIT_OUTCOME, Permission.VIEW_DASHBOARD
    },
    Role.READ_ONLY: {
        Permission.VIEW_CASE, Permission.VIEW_DASHBOARD
    },
    Role.SYSTEM: {
        Permission.CREATE_CASE, Permission.VIEW_CASE, Permission.SUBMIT_OUTCOME,
        Permission.VIEW_DASHBOARD, Permission.TRIGGER_ALERT
    }
}

def has_permission(role: str, permission: Permission) -> bool:
    try:
        r = Role(role)
        return permission in ROLE_PERMISSIONS.get(r, set())
    except ValueError:
        return False
