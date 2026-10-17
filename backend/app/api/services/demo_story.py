"""The demo story as data: what had happened to the pathway steps of the demo case by a given day.

DEMO ASSUMPTIONS, not clinical facts: order-confirmation and examination times are made up to fit the documents; the
result times are the receipt times of the seeded reports (`app.seed.demo_case.DOCUMENTS`, checked by a test). The
replay in `CoordinationService.replay_story` walks the real task state machine along these events; nothing is written
directly. Histology is promised for 15. 10. but its report (11) arrives on 19. 10., so on 16. 10. it is the only
overdue step.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Final

from app.domain import clock


def _at(month: int, day: int, hour: int, minute: int = 0) -> datetime:
    return datetime(2026, month, day, hour, minute, tzinfo=clock.TZ)


@dataclass(frozen=True)
class StoryStep:
    step: str  # pathway step id without the case prefix, e.g. "ct"
    confirmed_at: datetime  # order confirmed (place + date) and accepted
    scheduled_at: datetime  # the confirmed examination date
    result_at: datetime  # result delivered (receipt of the report)
    result_doc_id: str
    performed_at: datetime | None = None  # None: performed when the result arrives (e.g. histology)

    @property
    def examined_at(self) -> datetime:
        return self.performed_at or self.result_at


# In dependency order: the machine refuses to start a step before the steps it depends on are completed.
STORY: Final = (
    StoryStep("ct", _at(10, 5, 10), _at(10, 8, 8), _at(10, 8, 15, 30), "08_CT_KOC1_2026-10-08", _at(10, 8, 9)),
    StoryStep(
        "eus-fnb", _at(10, 8, 16), _at(10, 12, 9), _at(10, 12, 13), "09_Biopsie_vykon_KOC2_2026-10-12", _at(10, 12, 11)
    ),
    StoryStep("labs", _at(10, 12, 14), _at(10, 15, 8), _at(10, 15, 14), "10_Laborator_KOC2_2026-10-15", _at(10, 15, 9)),
    StoryStep("histology", _at(10, 12, 14), _at(10, 12, 13), _at(10, 19, 16), "11_Histologie_KOC2_2026-10-19"),
)
