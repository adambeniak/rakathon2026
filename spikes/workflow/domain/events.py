"""Shared vocabulary: roles and the events that state machines return as side effects.

Events are plain data. Persisting them (AuditEvent, notifications) is the caller's job.
Payloads carry ids and states only — never patient names or clinical content.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
from datetime import datetime
from enum import StrEnum
from typing import Any


class Role(StrEnum):
    GP = "gp"  # praktický lékař
    COORD = "coordinator"  # koordinátor/ka KOC
    KOC_DOC = "koc_doctor"  # lékař KOC
    MDT = "mdt"  # člen / předseda MDT
    REVIEWER = "reviewer"  # revizní lékař ZP
    SYSTEM = "system"


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


class TransitionError(Exception):
    """Forbidden transition. `code` + `detail` map 1:1 to an RFC 7807 problem later."""

    def __init__(self, code: str, detail: str) -> None:
        super().__init__(f"{code}: {detail}")
        self.code = code
        self.detail = detail
