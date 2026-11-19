"""
STEP 7: the smallest real user registry this repository has never had.

No user database exists anywhere in this codebase (confirmed during
diagnosis — see docs/product/AUTH_OPERATIONAL_COMPLETION_REPORT.md).
`hashlib.sha256` + a per-user salt is used rather than bcrypt/passlib
because neither is an existing dependency of this project and adding one
for five demo accounts is out of proportion to what this task asks for;
this is explicitly a DEMO/DEV registry, not a production credential store
— exactly as `apps.api.config.jwt_secret_key`'s own docstring already
discloses the same posture for the signing key. A real deployment needs a
real user store and a real password-hashing library; this closes the
narrower gap of "there is currently no way to log in at all."

Roles are read from THIS registry, server-side, never from the client —
`login()` returns the role that was stored at account-creation, and the
`/v1/auth/login` route below has no field a caller can use to name their
own role.
"""
from __future__ import annotations

import hashlib
import hmac
from dataclasses import dataclass


@dataclass(frozen=True)
class DemoUser:
    username: str
    role: str
    salt: str
    password_hash: str


def _hash(password: str, salt: str) -> str:
    return hashlib.sha256(f"{salt}:{password}".encode("utf-8")).hexdigest()


def _user(username: str, password: str, role: str) -> DemoUser:
    salt = f"varuna-demo-{username}"
    return DemoUser(username=username, role=role, salt=salt, password_hash=_hash(password, salt))


# Demo credentials, disclosed here in plain sight rather than hidden —
# this registry is not a secret boundary, the JWT signature is. One
# account per role this repository's RBAC table actually defines
# (varuna_infra.rbac.Role), so every role's permission set is reachable
# for demo/testing purposes.
_DEMO_USERS: dict[str, DemoUser] = {
    u.username: u
    for u in [
        _user("admin", "admin-demo-pass", "admin"),
        _user("officer", "officer-demo-pass", "duty_officer"),
        _user("analyst", "analyst-demo-pass", "analyst"),
        _user("field", "field-demo-pass", "field_operator"),
        _user("viewer", "viewer-demo-pass", "read_only"),
    ]
}


def authenticate(username: str, password: str) -> DemoUser | None:
    """Constant-time-compares the hash, not the raw password. Returns None
    on any mismatch (unknown user or wrong password) — deliberately the
    same failure shape for both, so a login attempt cannot be used to
    enumerate valid usernames."""
    user = _DEMO_USERS.get(username)
    if user is None:
        return None
    candidate = _hash(password, user.salt)
    if not hmac.compare_digest(candidate, user.password_hash):
        return None
    return user
