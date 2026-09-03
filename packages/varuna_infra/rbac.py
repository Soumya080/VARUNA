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
    # Running a case-workflow stage (ingest/reconstruct/attribute) on an
    # existing case. Distinct from CREATE_CASE so a future role could create
    # cases but not drive their scientific pipeline, or vice versa.
    RUN_CASE_STAGE = "run_case_stage"
    APPROVE_MISSION = "approve_mission"
    VIEW_CASE = "view_case"
    VIEW_SENSITIVE = "view_sensitive"
    MODIFY_CONFIG = "modify_config"
    MANAGE_USERS = "manage_users"
    SUBMIT_OUTCOME = "submit_outcome"
    APPROVE_MODEL = "approve_model"
    VIEW_DASHBOARD = "view_dashboard"
    TRIGGER_ALERT = "trigger_alert"
    # STEP 6: distinct from TRIGGER_ALERT (sending one) — these gate an
    # operator's own handling of an already-generated alert.
    ACKNOWLEDGE_ALERT = "acknowledge_alert"
    ESCALATE_ALERT = "escalate_alert"
    RESOLVE_ALERT = "resolve_alert"
    # Sending a real outbound message to verify credentials.
    # Admin-only: it costs money and reaches real people.
    TEST_NOTIFICATION = "test_notification"

ROLE_PERMISSIONS: dict[Role, Set[Permission]] = {
    Role.ADMIN: {
        Permission.CREATE_CASE, Permission.RUN_CASE_STAGE, Permission.APPROVE_MISSION,
        Permission.VIEW_CASE, Permission.VIEW_SENSITIVE, Permission.MODIFY_CONFIG,
        Permission.MANAGE_USERS, Permission.SUBMIT_OUTCOME, Permission.APPROVE_MODEL,
        Permission.VIEW_DASHBOARD, Permission.TRIGGER_ALERT,
        Permission.ACKNOWLEDGE_ALERT, Permission.ESCALATE_ALERT, Permission.RESOLVE_ALERT,
        Permission.TEST_NOTIFICATION,
    },
    Role.DUTY_OFFICER: {
        Permission.CREATE_CASE, Permission.RUN_CASE_STAGE, Permission.APPROVE_MISSION,
        Permission.VIEW_CASE, Permission.VIEW_SENSITIVE, Permission.SUBMIT_OUTCOME,
        Permission.VIEW_DASHBOARD, Permission.TRIGGER_ALERT,
        Permission.ACKNOWLEDGE_ALERT, Permission.ESCALATE_ALERT, Permission.RESOLVE_ALERT,
    },
    Role.ANALYST: {
        Permission.VIEW_CASE, Permission.VIEW_SENSITIVE, Permission.VIEW_DASHBOARD,
        Permission.ACKNOWLEDGE_ALERT,
    },
    Role.FIELD_OPERATOR: {
        Permission.VIEW_CASE, Permission.SUBMIT_OUTCOME, Permission.VIEW_DASHBOARD
    },
    Role.READ_ONLY: {
        Permission.VIEW_CASE, Permission.VIEW_DASHBOARD
    },
    Role.SYSTEM: {
        Permission.CREATE_CASE, Permission.RUN_CASE_STAGE, Permission.VIEW_CASE, Permission.SUBMIT_OUTCOME,
        Permission.VIEW_DASHBOARD, Permission.TRIGGER_ALERT
    }
}

def has_permission(role: str, permission: Permission) -> bool:
    try:
        r = Role(role)
        return permission in ROLE_PERMISSIONS.get(r, set())
    except ValueError:
        return False
