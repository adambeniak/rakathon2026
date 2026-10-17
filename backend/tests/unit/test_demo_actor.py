"""The person each demo role stands for, as recorded in Provenance / AuditEvent.

The frontend header names the same people (`frontend/src/mocks/fixtures/people.ts`, `AppShell.test.tsx`): the contract
has no "who am I" endpoint, so the names are mirrored there. If the seed or the mapping changes, change both.
"""

from __future__ import annotations

import pytest

from app.domain.common import Role
from app.fhir.directory import Directory
from app.security.actor import current_actor
from app.settings import Settings
from tests.directory_fixtures import demo_directory


class _Provider:
    async def get(self) -> Directory:
        return demo_directory()


@pytest.mark.parametrize(
    ("header", "role", "display"),
    [
        ("gp", Role.GP, "MUDr. Tomáš Řezníček"),
        ("coordinator", Role.COORDINATOR, "Bc. Lucie Dvořáková"),
        ("koc_physician", Role.KOC_PHYSICIAN, "doc. MUDr. Pavel Hrubý, Ph.D."),
        ("reviewer", Role.REVIEWER, "MUDr. Jitka Benešová"),
    ],
)
async def test_each_demo_role_maps_to_the_same_person(
    settings: Settings, header: str, role: Role, display: str
) -> None:
    actor = await current_actor(settings, _Provider(), header)  # type: ignore[arg-type]

    assert actor.role is role
    assert actor.display == display
