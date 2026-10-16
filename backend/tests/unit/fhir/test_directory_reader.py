from __future__ import annotations

from app.domain.common import Role
from tests.directory_fixtures import demo_directory


def test_demo_directory_round_trips_through_mappers() -> None:
    directory = demo_directory()

    assert [k.org.id for k in directory.kocs()] == ["koc1-nemocnice-severni", "koc2-nemocnice-lipova"]
    assert directory.insurer("211") is not None
    assert directory.role("reznicek-tomas@pl-dolni-brezany").role.role is Role.GP  # type: ignore[union-attr]


def test_role_holder_has_a_role_level_display_but_a_concrete_role_id() -> None:
    holder = demo_directory().role_holder("koc2-nemocnice-lipova", Role.COORDINATOR)

    assert holder is not None
    assert holder.id == "dvorakova-lucie@koc2-nemocnice-lipova"
    assert holder.display == "Koordinátor KOC 2"
    assert holder.role is Role.COORDINATOR


def test_koc_without_coordinator_has_no_holder() -> None:
    assert demo_directory().role_holder("koc1-nemocnice-severni", Role.COORDINATOR) is None
