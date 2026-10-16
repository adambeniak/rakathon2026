"""The current actor recorded in AuditEvent / Provenance."""

from __future__ import annotations

from app.domain.common import PartyRef, Role

SYSTEM_ACTOR = PartyRef(id="system", display="Štafeta (systém)", role=Role.SYSTEM)


def current_actor() -> PartyRef:
    """FastAPI dependency. TODO(#4): resolve the user from the mock login / role switcher instead of `system`."""
    return SYSTEM_ACTOR
