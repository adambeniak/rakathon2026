"""Facts of the GP letter -> an evidenced `ReferralPrefill` (owner: P2/P4; pure, no I/O, no LLM).

Only what the letter states is taken over, each value with the quote it was read from. The extraction already passed
the evidence lock, so every quote exists verbatim in the source. A value the letter does not state stays `missing`.
The only computed value is the sex, derived from the rodné číslo (marked `derived`, evidence = the RČ quote).
"""

from __future__ import annotations

import re
from collections.abc import Callable, Sequence
from datetime import date

from app.documents.normalize import find_dates
from app.domain.birth_number import parse_birth_number
from app.domain.evidence import Certainty, Evidence, Fact, FactType
from app.domain.patient import Address, ContactPerson, Sex
from app.domain.referral import Evidenced, FieldStatus, ReferralPrefill, SuspectedDiagnosis

_ADDRESS = re.compile(r"^(?P<line>.+?),\s*(?P<zip>\d{3}\s?\d{2})\s+(?P<city>.+)$")
_AGE = re.compile(r"^\d{1,3}\s*let$")
_INSURER = re.compile(r"^\d{3}$")
_GP_RELATION = "praktický lékař"


def _missing[T]() -> Evidenced[T]:
    return Evidenced[T](status=FieldStatus.MISSING)


def _found[T](value: T, fact: Fact, **extra: object) -> Evidenced[T]:
    return Evidenced[T](value=value, status=FieldStatus.COMPLETE, evidence=list(fact.evidence), **extra)  # type: ignore[arg-type]


def _field(value: object, key: str) -> str | None:
    if isinstance(value, dict):
        item = value.get(key)
        return item.strip() if isinstance(item, str) and item.strip() else None
    return None


def _kind(fact: Fact) -> str | None:
    return _field(fact.value, "kind")


def _quote(fact: Fact) -> str:
    return fact.evidence[0].quote


def _first(facts: Sequence[Fact], test: Callable[[Fact], bool]) -> Fact | None:
    return next((f for f in sorted(facts, key=_position) if test(f)), None)


def _position(fact: Fact) -> int:
    return fact.evidence[0].char_start if fact.evidence[0].char_start is not None else 1 << 30


def _person(fact: Fact) -> tuple[str | None, str | None, str | None]:
    return _field(fact.value, "name"), _field(fact.value, "relation"), _field(fact.value, "phone")


def _split_name(full: str) -> tuple[str, str]:
    """'Alena Procházková' -> ('Alena', 'Procházková'); titles are not expected for patients."""
    parts = full.split()
    return (" ".join(parts[:-1]), parts[-1]) if len(parts) > 1 else ("", full)


def _address(text: str) -> Address | None:
    match = _ADDRESS.match(text)
    if match is None:
        return None
    return Address(line=match["line"].strip(), postal_code=match["zip"].strip(), city=match["city"].strip())


def build_prefill(facts: Sequence[Fact], *, doc_id: str, authored_at: date | None) -> ReferralPrefill:
    identity = [f for f in facts if f.type is FactType.PATIENT_IDENTITY]
    contacts = [f for f in facts if f.type is FactType.CONTACT]

    name_fact = _first(identity, lambda f: _kind(f) == "person" and bool(_person(f)[0]))
    rc_fact = _first(
        identity, lambda f: _kind(f) == "text" and parse_birth_number(_field(f.value, "text") or "") is not None
    )
    date_fact = _first(
        identity, lambda f: _kind(f) == "date" and "narození" in (_field(f.value, "label") or "").lower()
    )
    age_fact = _first(identity, lambda f: _kind(f) == "text" and bool(_AGE.match(_field(f.value, "text") or "")))
    address_fact = _first(identity, lambda f: _kind(f) == "person" and bool(_field(f.value, "address")))
    insurer_fact = _first(
        [f for f in facts if f.type is FactType.INSURER],
        lambda f: bool(_INSURER.match(_field(f.value, "text") or "")),
    )
    phone_fact = _first(
        contacts,
        lambda f: (
            _kind(f) == "person"
            and not _person(f)[0]
            and bool(_person(f)[2])
            and _quote(f).lower().startswith("telefon")
        ),
    )
    contact_fact = _first(
        contacts,
        lambda f: (
            _kind(f) == "person"
            and bool(_person(f)[0])
            and bool(_person(f)[1])
            and _quote(f).lower().startswith("kontaktní osoba")
        ),
    )
    gp_fact = _first(contacts, lambda f: _kind(f) == "person" and (_person(f)[1] or "").lower() == _GP_RELATION)
    diagnosis_fact = _first(
        [f for f in facts if f.type is FactType.DIAGNOSIS],
        lambda f: _kind(f) == "coded" and f.certainty is Certainty.SUSPECTED and bool(_field(f.value, "code")),
    )
    urgency_fact = _first(
        [f for f in facts if f.type is FactType.REFERRAL_REQUEST], lambda f: "urgent" in _quote(f).lower()
    )
    consent_facts = sorted((f for f in facts if f.type is FactType.CONSENT_OR_WISH), key=_position)

    given_field: Evidenced[str] = _missing()
    family_field: Evidenced[str] = _missing()
    if name_fact is not None and (full := _person(name_fact)[0]):
        given, family = _split_name(full)
        given_field = _found(given, name_fact) if given else _missing()
        family_field = _found(family, name_fact)

    rc_text = _field(rc_fact.value, "text") if rc_fact else None
    rc_info = parse_birth_number(rc_text) if rc_text else None
    birth_number: Evidenced[str] = _found(rc_text, rc_fact) if rc_fact and rc_text else _missing()

    birth_date: Evidenced[date] = _missing()
    if date_fact is not None:
        parsed = _parse_date(date_fact)
        if parsed is not None:
            birth_date = _found(parsed, date_fact)
    if rc_info and rc_info.birth_date and birth_date.value and rc_info.birth_date != birth_date.value:
        note = "Datum narození v žádance nesouhlasí s datem z rodného čísla."
        birth_date = birth_date.model_copy(update={"status": FieldStatus.NEEDS_CLARIFICATION, "note": note})
        birth_number = birth_number.model_copy(update={"status": FieldStatus.NEEDS_CLARIFICATION, "note": note})

    if rc_info and rc_info.checksum_valid is False:
        note = "Kontrolní číslice rodného čísla nesouhlasí; ověřte."
        birth_number = birth_number.model_copy(update={"status": FieldStatus.NEEDS_CLARIFICATION, "note": note})

    sex: Evidenced[Sex] = _missing()
    if rc_fact is not None and rc_info and rc_info.sex is not None:
        sex = _found(rc_info.sex, rc_fact, derived=True, note="Pohlaví odvozeno z rodného čísla; potvrďte.")

    address_value = _address(_field(address_fact.value, "address") or "") if address_fact else None
    contact_value: ContactPerson | None = None
    if contact_fact is not None:
        name, relation, phone = _person(contact_fact)
        contact_value = ContactPerson(name=name or "", relation=relation or "", phone=phone)
    diagnosis_value: SuspectedDiagnosis | None = None
    if diagnosis_fact is not None:
        diagnosis_value = SuspectedDiagnosis(
            code=_field(diagnosis_fact.value, "code"), text=_field(diagnosis_fact.value, "text") or ""
        )

    return ReferralPrefill(
        doc_id=doc_id,
        authored_at=authored_at,
        given=given_field,
        family=family_field,
        sex=sex,
        birth_date=birth_date,
        age_text=_found(_field(age_fact.value, "text") or "", age_fact) if age_fact else _missing(),
        birth_number=birth_number,
        birth_number_checksum_valid=rc_info.checksum_valid if rc_info else None,
        address=_found(address_value, address_fact) if address_fact and address_value else _missing(),
        patient_phone=_found(_person(phone_fact)[2] or "", phone_fact) if phone_fact else _missing(),
        insurer_code=_found(_field(insurer_fact.value, "text") or "", insurer_fact) if insurer_fact else _missing(),
        contact_person=_found(contact_value, contact_fact) if contact_fact and contact_value else _missing(),
        requesting_gp=_found(_person(gp_fact)[0] or "", gp_fact) if gp_fact else _missing(),
        suspected_diagnosis=_found(diagnosis_value, diagnosis_fact)
        if diagnosis_fact and diagnosis_value
        else _missing(),
        consent_statements=[_found(_field(f.value, "text") or _quote(f), f) for f in consent_facts],
        urgency_statement=_found(_quote(urgency_fact), urgency_fact) if urgency_fact else _missing(),
    )


def _parse_date(fact: Fact) -> date | None:
    text = _field(fact.value, "date")
    if text:
        try:
            return date.fromisoformat(text)
        except ValueError:
            found = find_dates(text)
            if found:
                return found[0]
    return fact.clinical_date


def evidence_quotes(evidence: Sequence[Evidence]) -> list[str]:
    return [e.quote for e in evidence]
