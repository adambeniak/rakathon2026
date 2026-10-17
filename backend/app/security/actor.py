"""The current actor recorded in AuditEvent / Provenance (owner: P4). ONE shared dependency: `current_actor`.

Demo mock login, fail closed: the role switcher sends `X-Demo-Role` (a `Role` value). It is honoured only when
`STAFETA_DEMO_MODE=1`; the role is validated against the `Role` enum and mapped to a seeded person of that role from
the directory (the client never chooses a person or a role beyond the enum). Missing header in demo mode = coordinator.
Outside demo mode every request is 401: real authentication (#4) replaces this function and keeps its signature.
"""

from __future__ import annotations

from typing import Annotated

from fastapi import Header

from app.api.clients import DirectoryProviderDep, SettingsDep
from app.domain.common import PartyRef, Role
from app.domain.errors import UnauthenticatedError

DEMO_ROLE_HEADER = "X-Demo-Role"
DEFAULT_DEMO_ROLE = Role.COORDINATOR
# Roles that stand for a person at a workplace; `system` and `patient` can never be chosen from the browser.
DEMO_ROLES = frozenset({Role.GP, Role.COORDINATOR, Role.KOC_PHYSICIAN, Role.KOC_STAFF, Role.REVIEWER})
SYSTEM_ACTOR = PartyRef(id="system", display="Štafeta (systém)", role=Role.SYSTEM)


async def current_actor(
    settings: SettingsDep,
    directory: DirectoryProviderDep,
    x_demo_role: Annotated[str | None, Header(alias=DEMO_ROLE_HEADER, max_length=40)] = None,
) -> PartyRef:
    if not settings.stafeta_demo_mode:
        raise UnauthenticatedError("Je vyžadováno přihlášení")
    role = _parse_role(x_demo_role)
    entries = (await directory.get()).roles
    seeded = sorted((r for r in entries if r.role.role is role), key=lambda r: r.role.id)
    if not seeded:
        raise UnauthenticatedError("Pro tuto roli není v adresáři žádná osoba")
    return seeded[0].party()


def _parse_role(value: str | None) -> Role:
    if not value:
        return DEFAULT_DEMO_ROLE
    try:
        role = Role(value.strip().lower())
    except ValueError:
        raise UnauthenticatedError("Neznámá role") from None
    if role not in DEMO_ROLES:
        raise UnauthenticatedError("Tuto roli nelze zvolit")
    return role
