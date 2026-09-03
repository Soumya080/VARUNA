"""
VARUNA GRID — authorization enforcement boundary.

`varuna_infra.rbac.has_permission()` has existed and been unit-tested since
early in the project, and until now had **zero production call sites** — the
permission table was correct and never consulted. This module is the
enforcement point that closes that gap.

Design decision: enforcement lives at the **service** layer, not only in the
FastAPI router. A check that exists only in the HTTP layer is bypassed by
every non-HTTP caller — the Case Engine, a script, a Celery task, a test
helper — which is precisely the set of callers most likely to be automated.
`Principal` is threaded into the service call itself so that authorization is
part of the operation's contract rather than a property of how it was reached.

`AuditEntry` records every decision, allow *and* deny. A deny that leaves no
trace is indistinguishable from a request that was never made.
"""
from __future__ import annotations

import uuid
from datetime import datetime, timezone
from pathlib import Path

from pydantic import BaseModel, ConfigDict, Field

from varuna_infra.rbac import Permission, Role, has_permission


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


class AuthorizationError(PermissionError):
    """
    Raised when a principal lacks a required permission.

    Subclasses PermissionError so callers that already handle the builtin
    behave sensibly, and so it can never be silently caught by a bare
    `except ValueError` that was written for a different failure.
    """

    def __init__(self, principal_id: str, role: str, permission: Permission,
                 operation: str) -> None:
        self.principal_id = principal_id
        self.role = role
        self.permission = permission
        self.operation = operation
        super().__init__(
            f"principal {principal_id!r} with role {role!r} lacks permission "
            f"{permission.value!r} required for {operation!r}"
        )


class Principal(BaseModel):
    """
    Who is asking. Deliberately minimal: an id and a role are all the RBAC
    table needs, and carrying more (tokens, password hashes) through service
    calls would spread credential material across the codebase.
    """
    model_config = ConfigDict(extra="forbid", frozen=True)

    principal_id: str = Field(..., min_length=1)
    role: str = Field(..., min_length=1)

    @classmethod
    def system(cls) -> Principal:
        """
        The system's own identity for automated, non-human-initiated work.

        Note SYSTEM deliberately does NOT hold APPROVE_MISSION in
        `ROLE_PERMISSIONS`: automated pipelines can create and observe
        missions but cannot authorize one. That is the two-step human
        approval requirement expressed as a permission rather than as a
        convention, and it means an unattended pipeline physically cannot
        dispatch an asset.
        """
        return cls(principal_id="system", role=Role.SYSTEM.value)


class AuditEntry(BaseModel):
    """One authorization decision. Recorded whether or not it was allowed."""
    model_config = ConfigDict(extra="forbid")

    audit_id: str = Field(default_factory=lambda: f"aud-{uuid.uuid4().hex[:10]}")
    principal_id: str
    role: str
    permission: str
    operation: str
    allowed: bool
    subject_id: str | None = None          # e.g. the mission_id being acted on
    at: datetime = Field(default_factory=_utcnow)
    note: str | None = None


class AuditLog:
    """Authorization audit sink.

    Optionally disk-backed: pass `path=` and the trail survives a restart.
    An audit log that evaporates when the process exits cannot answer "who
    authorised this dispatch?" the next morning, which is the only question
    it exists to answer.

    Append-only on disk (never rewritten wholesale) so a crash part-way
    through a write cannot lose earlier decisions.
    """

    def __init__(self, path: "str | Path | None" = None) -> None:
        self._entries: list[AuditEntry] = []
        self._store = None
        if path is not None:
            from varuna_infra.jsonl_store import AppendJsonlStore

            self._store = AppendJsonlStore(
                path,
                loads=AuditEntry.model_validate_json,
                dumps=lambda e: e.model_dump_json(),
            )
            self._entries = self._store.all()

    @property
    def persisted(self) -> bool:
        return self._store is not None

    def record(self, entry: AuditEntry) -> AuditEntry:
        self._entries.append(entry)
        if self._store is not None:
            self._store.append(entry)
        return entry

    def all(self) -> list[AuditEntry]:
        return list(self._entries)

    def for_subject(self, subject_id: str) -> list[AuditEntry]:
        return [e for e in self._entries if e.subject_id == subject_id]

    def denials(self) -> list[AuditEntry]:
        return [e for e in self._entries if not e.allowed]


def authorize(principal: Principal, permission: Permission, operation: str, *,
              subject_id: str | None = None,
              audit: AuditLog | None = None) -> AuditEntry:
    """
    Enforce a permission. Returns the audit entry on success, raises
    `AuthorizationError` on failure — never returns a bool, because a bool
    return is the shape that gets accidentally ignored at a call site.
    """
    allowed = has_permission(principal.role, permission)
    entry = AuditEntry(
        principal_id=principal.principal_id, role=principal.role,
        permission=permission.value, operation=operation,
        allowed=allowed, subject_id=subject_id,
    )
    if audit is not None:
        audit.record(entry)
    if not allowed:
        raise AuthorizationError(principal.principal_id, principal.role,
                                 permission, operation)
    return entry
