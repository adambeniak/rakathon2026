"""Shared vocabulary: the events that state machines return as side effects.

Events are plain data. Persisting them (AuditEvent, notifications) is the caller's job.
Payloads carry ids and states only — never patient names or clinical content.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from datetime import datetime
from enum import StrEnum
from typing import Any

from app.domain.common import Role
from app.domain.errors import ConflictError


class EventKind(StrEnum):
    AUDIT = "audit"
    NOTIFICATION = "notification"
    ESCALATION = "escalation"


@dataclass(frozen=True)
class DomainEvent:
    kind: EventKind
    action: str  # audit: verb (create/update/read/...); notification/escalation: template code
    at: datetime
    payload: Mapping[str, Any] = field(default_factory=dict)
    recipients: tuple[Role, ...] = ()


class TransitionError(ConflictError):
    """Forbidden transition. `code` + `detail` map 1:1 to an RFC 7807 problem later.

    `blocking_items` (readiness item keys) is set only when a guard can name what blocks it in structured form
    (`mark_ready_mdt`); `detail` is a human sentence and must never be parsed.
    """

    def __init__(self, code: str, detail: str, blocking_items: Sequence[str] | None = None) -> None:
        super().__init__(f"{code}: {detail}")
        self.code = code
        self.detail = detail
        self.blocking_items: tuple[str, ...] | None = tuple(blocking_items) if blocking_items is not None else None
