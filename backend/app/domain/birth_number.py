"""Rodné číslo (RČ): date of birth, sex and checksum, derived deterministically (see the czech-clinical-docs skill)."""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import date

from app.domain.patient import Sex

_RC = re.compile(r"^(\d{2})(\d{2})(\d{2})/?(\d{3,4})$")


@dataclass(frozen=True)
class BirthNumberInfo:
    birth_date: date | None
    sex: Sex | None
    checksum_valid: bool | None  # None: 9-digit (pre-1954) numbers have no checksum


def parse_birth_number(value: str) -> BirthNumberInfo | None:
    """None when the text is not shaped like an RČ."""
    match = _RC.match(value.strip())
    if match is None:
        return None
    yy, mm, dd, tail = int(match[1]), int(match[2]), int(match[3]), match[4]
    ten_digits = len(tail) == 4
    sex = Sex.FEMALE if mm > 50 else Sex.MALE
    month = mm - 50 if mm > 50 else mm
    if month > 20:  # +20 overflow series
        month -= 20
    year = (1900 + yy if yy >= 54 else 2000 + yy) if ten_digits else 1900 + yy  # 9 digits: issued before 1954
    try:
        birth = date(year, month, dd)
    except ValueError:
        birth = None
    checksum: bool | None = None
    if ten_digits:
        number = int(f"{match[1]}{match[2]}{match[3]}{tail}")
        first_nine = number // 10
        remainder = first_nine % 11
        checksum = (remainder == 10 and number % 10 == 0) or number % 11 == 0
    return BirthNumberInfo(birth_date=birth, sex=sex, checksum_valid=checksum)
