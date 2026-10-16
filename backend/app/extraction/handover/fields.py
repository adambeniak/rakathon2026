"""One rule per handover field (Handover_obsah). Pure functions over the included facts.

Rules never fill a value the sources do not state: a missing value carries a `MissingItem` with a neutral reason
and the role expected to supply it. All texts are copied from evidence-locked fact values (verbatim). The only
derived values are deterministic code-list lookups on stated values (sex and checksum from the rodné číslo,
insurer name from the insurer code, age at as_of).
"""

from __future__ import annotations

import re
from collections.abc import Callable, Sequence
from datetime import date, timedelta
from typing import Final, Literal

from app.domain.common import Role
from app.domain.evidence import Certainty, Fact, FactType
from app.domain.handover import (
    ComorbiditiesField,
    Comorbidity,
    ContactPerson,
    Contacts,
    ContactsField,
    Diagnosis,
    DiagnosisField,
    Examination,
    ExaminationsField,
    HandoverFieldBase,
    HandoverItem,
    HandoverStatus,
    Histology,
    HistologyField,
    LabResult,
    LabsField,
    Medication,
    MedicationsField,
    MissingItem,
    PatientField,
    PatientIdentity,
    PerformanceStatus,
    PerformanceStatusField,
    Symptoms,
    SymptomsField,
    TextField,
    TextListField,
    WeightHeight,
    WeightHeightField,
    WeightMeasurement,
)
from app.domain.patient import Patient, Sex
from app.extraction.handover.facts import (
    LOINC_IMAGING,
    LOINC_LAB_REPORT,
    LOINC_PATHOLOGY,
    LOINC_PROCEDURE_NOTE,
    LOINC_REFERRAL_NOTE,
    Context,
    cz_date,
    dedupe_by_text,
    fold_text,
    make_item,
    quantity,
    same_stem,
    text_of,
    tokens,
    union_evidence,
    value_of,
)
from app.extraction.values import CodedValue, DateValue, MedicationValue, PersonValue

NOT_STATED: Final = "v dokumentaci neuvedeno"
STATED: Final = (Certainty.STATED,)

# Kód zdravotní pojišťovny -> name (public code list; only codes used by the demo are needed).
INSURERS: Final = {
    "111": "Všeobecná zdravotní pojišťovna ČR",
    "201": "Vojenská zdravotní pojišťovna ČR",
    "205": "Česká průmyslová zdravotní pojišťovna",
    "207": "Oborová zdravotní pojišťovna",
    "209": "Zaměstnanecká pojišťovna Škoda",
    "211": "Zdravotní pojišťovna ministerstva vnitra ČR",
    "213": "RBP, zdravotní pojišťovna",
}

FAMILY_RELATIONS: Final = (
    "dcer", "syn", "manžel", "partner", "druh", "družk", "sestr", "bratr", "matk", "otec", "vnu", "snach", "zeť",
)  # fmt: skip
BIRTH_NUMBER = re.compile(r"^(\d{2})(\d{2})(\d{2})/?(\d{3,4})$")
INSURER_CODE = re.compile(r"(?<!\d)(\d{3})(?!\d)")
MORPHOLOGY = re.compile(r"^\d{4}/\d$")
TNM = re.compile(r"(?<![A-Za-z])[cpy]?T[0-4isx][a-d]?\s*N[0-3x][a-c]?\s*M[01x]?")
REPORT_ID = re.compile(r"\b[A-Z]{1,3}-\d{4}/\d+\b")
GRADE = re.compile(r"\bG[1-4](?:\s*[–-]\s*G[1-4])?\b")
IHC = re.compile(r"^([A-Z][A-Za-z0-9-]{1,12})\s+(.+?)\.?$")
COURSE_DAYS = re.compile(r"po\s+dobu\s+(\d+)\s+dn", re.IGNORECASE)
GENERIC_MDT_REQUEST = re.compile(r"stanovení\s+dalšího\s+postupu", re.IGNORECASE)
EXPLICIT_QUESTION = re.compile(r"\?|(?<!\w)zda(?!\w)|otázk\w*|posouzen\w*|resekabil\w*", re.IGNORECASE)
# Symptoms come from clinical notes; imaging/lab/pathology reports only restate the clinical question.
NON_SYMPTOM_DOCS: Final = frozenset({LOINC_IMAGING, LOINC_LAB_REPORT, LOINC_PATHOLOGY})
DOCUMENTED_PREFIX: Final = "Uvedeno v dokumentaci"
TUMOUR_MARKERS: Final = ("ca 19-9", "cea", "ca 125", "ca 15-3", "afp", "psa", "ca 72-4")


def _missing(item: str, owner: Role, reason: str = NOT_STATED) -> MissingItem:
    return MissingItem(item=item, reason=reason, suggested_owner=owner)


def _with_missing[FieldT: HandoverFieldBase](field: FieldT, missing: Sequence[MissingItem]) -> FieldT:
    """Set both `missing` (item keys, shared with data/golden) and `missing_items` (reason + owner)."""
    if not missing:
        return field
    return field.model_copy(update={"missing": [m.item for m in missing], "missing_items": list(missing)})


def documented(ctx: Context, fact: Fact) -> str:
    """A plan or instruction written by a document's author, attributed so it never reads as Štafeta's advice."""
    doc = ctx.docs[fact.doc_id]
    return f"{DOCUMENTED_PREFIX} ({doc.title}, {cz_date(doc.authored_at)}): {text_of(fact)}"


# ---------------------------------------------------------------- 1 patient


def birth_number_info(birth_number: str) -> tuple[Sex, bool] | None:
    """Sex (month + 50 / + 70 = female) and checksum validity (10 digits divisible by 11) of a rodné číslo."""
    m = BIRTH_NUMBER.match(birth_number.strip())
    if m is None:
        return None
    month = int(m.group(2))
    sex = Sex.FEMALE if month > 50 else Sex.MALE
    digits = "".join(m.groups())
    valid = len(digits) == 10 and int(digits) % 11 == 0
    return sex, valid


SEX_CS: Final = {Sex.FEMALE: "žena", Sex.MALE: "muž", Sex.OTHER: "jiné", Sex.UNKNOWN: "neuvedeno"}


def patient_field(ctx: Context) -> PatientField:
    identity = ctx.select([FactType.PATIENT_IDENTITY], fields=[1])
    used: list[Fact] = []

    def latest(pred: Callable[[Fact], bool]) -> Fact | None:
        found = ctx.latest(f for f in identity if pred(f))
        if found is not None:
            used.append(found)
        return found

    name = latest(lambda f: isinstance(v := value_of(f), PersonValue) and bool(v.name))
    born = latest(lambda f: isinstance(v := value_of(f), DateValue) and "naroz" in v.label.casefold())
    rc = latest(lambda f: isinstance(v := value_of(f), CodedValue) and bool(BIRTH_NUMBER.match(v.code or "")))
    address = latest(lambda f: isinstance(v := value_of(f), PersonValue) and bool(v.address))
    insurer_fact = ctx.latest(f for f in ctx.select([FactType.INSURER], fields=[1]) if _insurer_code(f))
    if insurer_fact is not None:
        used.append(insurer_fact)

    missing: list[MissingItem] = []
    name_v = value_of(name) if name else None
    born_v = value_of(born) if born else None
    if not isinstance(name_v, PersonValue) or not name_v.name or not isinstance(born_v, DateValue):
        missing.append(_missing("name_or_birth_date", Role.COORDINATOR))
        return _with_missing(PatientField(status=HandoverStatus.MISSING, evidence=union_evidence(used)), missing)

    assert name is not None  # noqa: S101 - name_v is set
    assert born is not None  # noqa: S101 - born_v is set
    given, _, family = name_v.name.strip().rpartition(" ")
    birth_date = date.fromisoformat(born_v.date)
    rc_v = value_of(rc) if rc else None
    birth_number = rc_v.code if isinstance(rc_v, CodedValue) else None
    info = birth_number_info(birth_number) if birth_number else None
    insurer_code = _insurer_code(insurer_fact) if insurer_fact else None
    address_v = value_of(address) if address else None
    as_of_day = ctx.as_of.date()
    had_birthday = (as_of_day.month, as_of_day.day) >= (birth_date.month, birth_date.day)
    value = PatientIdentity(
        given=given or name_v.name,
        family=family,
        sex=info[0] if info else Sex.UNKNOWN,
        birth_date=birth_date,
        age_years=as_of_day.year - birth_date.year - (0 if had_birthday else 1),
        birth_number=birth_number,
        birth_number_checksum_valid=info[1] if info else None,
        insurer_code=insurer_code,
        insurer_name=INSURERS.get(insurer_code) if insurer_code else None,
        address=address_v.address if isinstance(address_v, PersonValue) else None,
    )
    items = [
        make_item(ctx, name_v.name, [name], label="Jméno"),
        make_item(ctx, cz_date(birth_date), [born], label="Datum narození"),
        make_item(ctx, value.age_years or 0, [born], label="Věk k datu předávky (vypočteno)", unit="let"),
    ]
    if rc is not None and birth_number:
        items.append(make_item(ctx, birth_number, [rc], label="Rodné číslo"))
        if info:
            items.append(make_item(ctx, SEX_CS[info[0]], [rc], label="Pohlaví (odvozeno z rodného čísla)"))
    if insurer_fact is not None and insurer_code:
        items.append(make_item(ctx, insurer_code, [insurer_fact], label="Zdravotní pojišťovna"))
        if value.insurer_name:
            items.append(make_item(ctx, value.insurer_name, [insurer_fact], label="Název pojišťovny (číselník)"))
    if address is not None and value.address:
        items.append(make_item(ctx, value.address, [address], label="Adresa"))
    if birth_number is None:
        missing.append(_missing("birth_number", Role.COORDINATOR))
    if insurer_code is None:
        missing.append(_missing("insurer_code", Role.COORDINATOR))
    if value.address is None:
        missing.append(_missing("address", Role.COORDINATOR))
    status = HandoverStatus.PARTIAL if missing else HandoverStatus.COMPLETE
    return _with_missing(
        PatientField(
            status=status,
            value=value,
            items=items,
            evidence=union_evidence(used),
            note="Pohlaví odvozeno z rodného čísla; název pojišťovny z číselníku." if info else None,
        ),
        missing,
    )


def _insurer_code(fact: Fact) -> str | None:
    v = value_of(fact)
    candidates = [v.code, v.text] if isinstance(v, CodedValue) else [text_of(fact)]
    for c in candidates:
        if c and (m := INSURER_CODE.search(c)):
            return m.group(1)
    return None


# ---------------------------------------------------------------- 2 contacts


def _digits(phone: str) -> str:
    return re.sub(r"\D", "", phone)[-9:]


def _person(f: Fact) -> PersonValue:
    v = value_of(f)
    assert isinstance(v, PersonValue)  # noqa: S101 - callers filter person facts
    return v


def contacts_field(ctx: Context, patient: Patient | None) -> ContactsField:
    persons = [f for f in ctx.select([FactType.CONTACT], fields=[2]) if isinstance(value_of(f), PersonValue)]
    used: list[Fact] = []
    items: list[HandoverItem] = []

    family = [f for f in persons if (r := _person(f).relation) and r.casefold().startswith(FAMILY_RELATIONS)]
    contact = ctx.latest(f for f in family if _person(f).name)
    contact_person = None
    if contact is not None:
        used.append(contact)
        cv = _person(contact)
        contact_person = ContactPerson(name=cv.name or "", relation=cv.relation or "", phone=cv.phone)
        items.append(make_item(ctx, text_of(contact), [contact], label="Kontaktní osoba"))

    # Patient phone: the registered phone if a document states it; else the only unnamed phone in the documents.
    unnamed = [f for f in persons if _person(f).phone and not _person(f).name and not _person(f).relation]
    note = None
    patient_phone_fact: Fact | None = None
    if patient is not None and patient.phone:
        registered = _digits(patient.phone)
        patient_phone_fact = ctx.latest(f for f in unnamed if _digits(_person(f).phone or "") == registered)
    if patient_phone_fact is None:
        numbers = {_digits(_person(f).phone or "") for f in unnamed}
        if len(numbers) == 1:
            patient_phone_fact = ctx.latest(unnamed)
        elif len(numbers) > 1:
            note = "V dokumentaci více telefonních čísel bez jména; telefon pacienta nelze jednoznačně určit."
    if patient_phone_fact is not None:
        used.append(patient_phone_fact)
        items.insert(0, make_item(ctx, _person(patient_phone_fact).phone or "", [patient_phone_fact], label="Telefon"))

    email_fact = ctx.latest(f for f in persons if _person(f).email and not _person(f).relation)
    if email_fact is not None:
        used.append(email_fact)
        items.append(make_item(ctx, _person(email_fact).email or "", [email_fact], label="E-mail"))

    value = Contacts(
        patient_phone=_person(patient_phone_fact).phone if patient_phone_fact else None,
        patient_email=_person(email_fact).email if email_fact else None,
        contact_person=contact_person,
    )
    missing = []
    if value.patient_phone is None:
        missing.append(_missing("patient_phone", Role.COORDINATOR))
    if value.patient_email is None:
        missing.append(_missing("patient_email", Role.COORDINATOR))
    if value.contact_person is None:
        missing.append(_missing("contact_person", Role.COORDINATOR))
    if len(missing) == 3:
        return _with_missing(ContactsField(status=HandoverStatus.MISSING, note=note), missing)
    status = HandoverStatus.PARTIAL if missing else HandoverStatus.COMPLETE
    field = ContactsField(status=status, value=value, items=items, evidence=union_evidence(used), note=note)
    return _with_missing(field, missing)


# ---------------------------------------------------------------- 3 diagnosis


def diagnosis_field(ctx: Context) -> DiagnosisField:
    candidates = ctx.select([FactType.DIAGNOSIS, FactType.HISTOLOGY], fields=[3, 14])
    coded = [(f, v) for f in candidates if isinstance(v := value_of(f), CodedValue) and v.code]
    icd = ctx.latest(f for f, v in coded if v.system == "MKN-10" and (v.code or "").upper().startswith(("C", "D0")))
    morph = ctx.latest(
        f for f, v in coded if v.system == "MKN-O" and MORPHOLOGY.match(v.code or "") and f.certainty == "stated"
    )
    if icd is None and morph is None:
        return _with_missing(DiagnosisField(status=HandoverStatus.MISSING), [_missing("diagnosis", Role.KOC_PHYSICIAN)])

    icd_v, morph_v = (value_of(icd) if icd else None), (value_of(morph) if morph else None)
    assert icd_v is None or isinstance(icd_v, CodedValue)  # noqa: S101 - selected as coded
    assert morph_v is None or isinstance(morph_v, CodedValue)  # noqa: S101
    verified = ctx.authored(morph) if morph and ctx.doc_type(morph) == LOINC_PATHOLOGY else None
    tnm_fact = next((f for f in ctx.facts if TNM.search(f.evidence[0].quote)), None)
    tnm_match = TNM.search(tnm_fact.evidence[0].quote) if tnm_fact else None
    used = [f for f in (icd, morph, tnm_fact) if f is not None]
    value = Diagnosis(
        icd10=icd_v.code if icd_v else None,
        text=morph_v.text if morph_v else (icd_v.text if icd_v else ""),
        icdo3_morphology=morph_v.code if morph_v else None,
        verified_histologically_on=verified,
        tnm=tnm_match.group(0) if tnm_match else None,
    )
    items: list[HandoverItem] = []
    if icd is not None and icd_v is not None:
        label = "MKN-10 (v dokumentu uvedeno jako suspektní)" if icd.certainty == Certainty.SUSPECTED else "MKN-10"
        items.append(make_item(ctx, icd_v.code or "", [icd], label=label))
    if morph is not None and morph_v is not None:
        items.append(make_item(ctx, morph_v.text, [morph], label="Histologie", clinical_date=verified))
        items.append(make_item(ctx, morph_v.code or "", [morph], label="MKN-O morfologie"))
    if tnm_fact is not None and value.tnm:
        items.append(make_item(ctx, value.tnm, [tnm_fact], label="TNM"))
    missing: list[MissingItem] = []
    if value.icd10 is None:
        missing.append(_missing("icd10", Role.KOC_PHYSICIAN))
    if value.icdo3_morphology is None:
        missing.append(_missing("histology", Role.KOC_PHYSICIAN))
    if value.tnm is None:
        missing.append(_missing("tnm_clinical_stage", Role.KOC_PHYSICIAN))
    note = None
    if icd is not None and icd.certainty == Certainty.SUSPECTED:
        note = f"Kód MKN-10 je v dokumentu {icd.doc_id} uveden jako suspektní."
    status = HandoverStatus.PARTIAL if missing else HandoverStatus.COMPLETE
    field = DiagnosisField(status=status, value=value, items=items, evidence=union_evidence(used), note=note)
    return _with_missing(field, missing)


# ---------------------------------------------------------------- 5 MDT question


def mdt_question_field(ctx: Context) -> TextField:
    requests = ctx.select([FactType.REFERRAL_REQUEST], fields=[5])
    referral_docs = {f.doc_id for f in requests if ctx.doc_type(f) == LOINC_REFERRAL_NOTE}
    if not referral_docs:
        missing = [_missing("mdt_question", Role.GP)]
        return _with_missing(TextField(status=HandoverStatus.MISSING), missing)
    latest_doc = max(referral_docs, key=lambda d: (ctx.docs[d].authored_at, d))
    facts = sorted((f for f in requests if f.doc_id == latest_doc), key=lambda f: f.evidence[0].char_start or 0)
    text = " ".join(text_of(f) for f in facts)
    evidence = union_evidence(facts)
    items = [make_item(ctx, text_of(f), [f], clinical_date=ctx.authored(f)) for f in facts]
    if GENERIC_MDT_REQUEST.search(text) and not EXPLICIT_QUESTION.search(text):
        missing = [_missing("explicit_mdt_question", Role.GP, "v žádosti chybí konkrétní otázka pro MDT")]
        return _with_missing(
            TextField(
                status=HandoverStatus.NEEDS_CLARIFICATION,
                value=text,
                items=items,
                evidence=evidence,
                note="Žádost uvádí pouze obecné „stanovení dalšího postupu“; konkrétní otázka pro MDT chybí.",
            ),
            missing,
        )
    return TextField(status=HandoverStatus.COMPLETE, value=text, items=items, evidence=evidence)


# ---------------------------------------------------------------- 6 comorbidities

MAX_CONTEXT_QUOTE = 60


def comorbidities_field(ctx: Context) -> ComorbiditiesField:
    facts = ctx.select([FactType.COMORBIDITY, FactType.DIAGNOSIS], fields=[6], certainties=STATED)
    coded = [f for f in facts if isinstance(v := value_of(f), CodedValue) and v.code]
    groups: list[list[Fact]] = []
    # Coded entries first: they become group heads and absorb text-only restatements.
    for fact in ctx.chronological(coded) + ctx.chronological(f for f in facts if f not in coded):
        group = _comorbidity_group(fact, groups, coded)
        if group is None:
            groups.append([fact])
        else:
            group.append(fact)
    if not groups:
        return _with_missing(ComorbiditiesField(status=HandoverStatus.MISSING), [_missing("comorbidities", Role.GP)])
    rows: list[Comorbidity] = []
    items: list[HandoverItem] = []
    for group in groups:
        head = group[0]
        hv = value_of(head)
        icd = hv.code if isinstance(hv, CodedValue) and hv.system == "MKN-10" else None
        longest = max((text_of(f) for f in group[1:]), key=len, default=None)
        detail = longest if longest and not tokens(longest) <= tokens(text_of(head)) else None
        quote = head.evidence[0].quote
        if detail is None and icd is None and len(quote) <= MAX_CONTEXT_QUOTE and len(quote) > len(text_of(head)) + 5:
            detail = quote  # a short fragment ("myomy") is shown with its source context, verbatim
        rows.append(Comorbidity(text=text_of(head), icd10=icd, detail=detail))
        items.append(make_item(ctx, text_of(head), group, label=icd))
    return ComorbiditiesField(status=HandoverStatus.COMPLETE, value=rows, items=items, evidence=union_evidence(facts))


def _comorbidity_group(fact: Fact, groups: list[list[Fact]], coded: list[Fact]) -> list[Fact] | None:
    t = tokens(text_of(fact))
    for g in groups:
        head = tokens(text_of(g[0]))
        if t <= head or head <= t:
            return g
    if fact in coded:
        return None
    # A text-only restatement sharing a distinctive word with exactly one coded entry ("Hypertenze kompenzovaná" ~
    # "Arteriální hypertenze") joins it.
    long_words = {w for w in t if len(w) >= 6}
    matches = [g for g in groups if g[0] in coded and long_words & tokens(text_of(g[0]))]
    return matches[0] if len(matches) == 1 else None


# ---------------------------------------------------------------- 7 medications


def medications_field(ctx: Context) -> MedicationsField:
    stated = ctx.select([FactType.MEDICATION], fields=[7], certainties=STATED)
    # Drugs in procedure notes (sedation, a pause before the procedure) are not the patient's medication list;
    # they are pointed to in the note so the pause stays visible.
    procedural = [f for f in stated if ctx.doc_type(f) == LOINC_PROCEDURE_NOTE]
    facts = [f for f in stated if f not in procedural]
    groups: list[list[Fact]] = []
    for fact in ctx.chronological(facts):
        drug = _med(fact).drug
        group = next((g for g in groups if same_stem(drug, _med(g[0]).drug)), None)
        if group is None:
            groups.append([fact])
        else:
            group.append(fact)
    rows: list[Medication] = []
    items: list[HandoverItem] = []
    used: list[Fact] = []
    notes: list[str] = []
    plans = ctx.select([FactType.DOCUMENTED_PLAN])
    for group in groups:
        # Latest complete entry wins (dose + schedule), else the latest entry.
        complete = [f for f in group if _med(f).dose and _med(f).schedule]
        head = ctx.latest(complete) or ctx.latest(group)
        assert head is not None  # noqa: S101 - groups are never empty
        hv = _med(head)
        if (days := _course_days(ctx, head)) is not None:
            notes.append(
                f"{hv.drug}: v dokumentaci předepsán na {days} dní od {cz_date(ctx.when(head))}; k datu předávky "
                "lhůta uplynula (výpočet systému), proto neuveden."
            )
            continue
        rows.append(Medication(drug=hv.drug, dose=hv.dose, schedule=hv.schedule))
        items.append(make_item(ctx, " ".join(p for p in (hv.dose, hv.schedule) if p) or hv.drug, group, label=hv.drug))
        used.extend(group)
        related = [f for f in procedural + plans if _first_word_like(text_of(f), hv.drug)]
        sources = sorted({f.doc_id for f in related}, key=lambda d: (ctx.docs[d].authored_at, d))
        if sources:
            where = "; ".join(f"{ctx.docs[d].title}, {cz_date(ctx.docs[d].authored_at)}" for d in sources)
            notes.append(f"{hv.drug}: viz dokumentované pokyny k podávání ({where}).")
    note = " ".join(notes) or None
    if not rows:
        missing = [_missing("medications", Role.GP)]
        return _with_missing(MedicationsField(status=HandoverStatus.MISSING, note=note), missing)
    return MedicationsField(
        status=HandoverStatus.COMPLETE, value=rows, items=items, evidence=union_evidence(used), note=note
    )


def _first_word_like(text: str, drug: str) -> str:
    """The word of `text` that matches `drug` by stem, else '' (drug mentions inside plans and procedure notes)."""
    return next((w for w in fold_text(text).split() if same_stem(w, drug)), "")


def _med(fact: Fact) -> MedicationValue:
    v = value_of(fact)
    assert isinstance(v, MedicationValue)  # noqa: S101 - medication facts carry medication values (lock)
    return v


def _course_days(ctx: Context, fact: Fact) -> int | None:
    """N of a stated 'po dobu N dní' course whose period lies before as_of, else None."""
    m = COURSE_DAYS.search(_med(fact).schedule or "")
    if m is None or ctx.when(fact) + timedelta(days=int(m.group(1))) >= ctx.as_of.date():
        return None
    return int(m.group(1))


# ---------------------------------------------------------------- 8 allergies, 9 performance status


def allergies_field(ctx: Context) -> TextField:
    fact = ctx.latest(ctx.select([FactType.ALLERGY], fields=[8]))
    if fact is None:
        return _with_missing(TextField(status=HandoverStatus.MISSING), [_missing("allergies", Role.GP)])
    return TextField(
        status=HandoverStatus.COMPLETE,
        value=text_of(fact),
        items=[make_item(ctx, text_of(fact), [fact])],
        evidence=union_evidence([fact]),
    )


def performance_status_field(ctx: Context) -> PerformanceStatusField:
    fact = ctx.latest(ctx.select([FactType.PERFORMANCE_STATUS], fields=[9], certainties=STATED))
    if fact is None:
        missing = [_missing("ecog", Role.KOC_PHYSICIAN, "ECOG/Karnofsky v dokumentaci neuvedeno")]
        return _with_missing(
            PerformanceStatusField(
                status=HandoverStatus.MISSING,
                note="Stav výkonnosti se z popisných údajů neodvozuje; doplní ošetřující lékař KOC.",
            ),
            missing,
        )
    quote = fact.evidence[0].quote
    q = quantity(fact)
    shown = (q.text_value or (str(int(q.number)) if q.number is not None else "")) if q else text_of(fact)
    scale: Literal["ECOG", "Karnofsky"] = "Karnofsky" if "karnofsk" in quote.casefold() else "ECOG"
    return PerformanceStatusField(
        status=HandoverStatus.COMPLETE,
        value=PerformanceStatus(scale=scale, value=shown or text_of(fact)),
        items=[make_item(ctx, shown or text_of(fact), [fact], label=scale, clinical_date=ctx.when(fact))],
        evidence=union_evidence([fact]),
    )


# ---------------------------------------------------------------- 10 weight and height


def weight_height_field(ctx: Context) -> WeightHeightField:
    vitals = ctx.select([FactType.VITAL_SIGN], certainties=STATED)
    weights = [f for f in vitals if (q := quantity(f)) and q.number is not None and _is(q.name, "hmotnost", "váha")]
    heights = [f for f in vitals if (q := quantity(f)) and q.number is not None and _is(q.name, "výška")]
    if not weights and not heights:
        both = [_missing("weight", Role.KOC_STAFF), _missing("height", Role.KOC_STAFF)]
        return _with_missing(WeightHeightField(status=HandoverStatus.MISSING), both)
    measured: dict[tuple[float, date], Fact] = {}
    for f in ctx.chronological(weights):
        q = quantity(f)
        assert q is not None  # noqa: S101 - filtered above
        assert q.number is not None  # noqa: S101
        measured.setdefault((q.number, ctx.when(f)), f)
    ordered = sorted(measured.items(), key=lambda kv: kv[0][1])
    series = [WeightMeasurement(kg=kg, date=day) for (kg, day), _ in ordered]
    items = [make_item(ctx, kg, [f], label="Hmotnost", unit="kg", clinical_date=day) for (kg, day), f in ordered]
    height = ctx.latest(heights)
    hq = quantity(height) if height else None
    if height is not None and hq is not None and hq.number is not None:
        items.insert(0, make_item(ctx, hq.number, [height], label="Výška", unit="cm", clinical_date=ctx.when(height)))
    value = WeightHeight(
        height_cm=hq.number if hq else None,
        height_date=ctx.when(height) if height else None,
        weights=series,
    )
    missing: list[MissingItem] = []
    status = HandoverStatus.COMPLETE
    note = None
    if not series:
        missing.append(_missing("weight", Role.KOC_STAFF))
        status = HandoverStatus.PARTIAL
    elif (ctx.as_of.date() - series[-1].date).days > ctx.rules.stale_vitals_days:
        status = HandoverStatus.STALE
        note = (
            f"Poslední hmotnost je z {cz_date(series[-1].date)}, starší než "
            f"{ctx.rules.stale_vitals_days} dní (demo pravidlo)."
        )
        missing.append(_missing("current_weight", Role.KOC_STAFF, "aktuální hmotnost v dokumentaci neuvedena"))
    if hq is None:
        missing.append(_missing("height", Role.KOC_STAFF))
        status = HandoverStatus.PARTIAL if status == HandoverStatus.COMPLETE else status
    used = list(measured.values()) + ([height] if height else [])
    field = WeightHeightField(status=status, value=value, items=items, evidence=union_evidence(used), note=note)
    return _with_missing(field, missing)


def _is(name: str, *stems: str) -> bool:
    return fold_text(name).startswith(stems)


# ---------------------------------------------------------------- 11 symptoms


def symptoms_field(ctx: Context) -> SymptomsField:
    """Stated and negated symptoms from clinical notes, each dated; negations are self-contained statements
    ("Teploty od září neměla."), shown verbatim so a later absence is not lost."""
    candidates = ctx.select([FactType.SYMPTOM], fields=[11], certainties=(Certainty.STATED, Certainty.NEGATED))
    facts = dedupe_by_text(ctx, [f for f in candidates if ctx.doc_type(f) not in NON_SYMPTOM_DOCS])
    if not facts:
        return _with_missing(SymptomsField(status=HandoverStatus.MISSING), [_missing("symptoms", Role.GP)])
    # Onset: the earliest stated symptom the documents date before they were written (a reported past onset).
    reported = [
        f
        for f in facts
        if f.certainty == Certainty.STATED and f.clinical_date is not None and f.clinical_date < ctx.authored(f)
    ]
    onset = min(reported, key=ctx.order_key) if reported else None
    items = [make_item(ctx, text_of(f), [f], clinical_date=ctx.when(f)) for f in facts]
    if onset is not None:
        items.insert(0, make_item(ctx, text_of(onset), [onset], label="Počátek obtíží", clinical_date=ctx.when(onset)))
    return SymptomsField(
        status=HandoverStatus.COMPLETE,
        value=Symptoms(onset=text_of(onset) if onset else None, items=[text_of(f) for f in facts]),
        items=items,
        evidence=union_evidence(facts),
    )


# ---------------------------------------------------------------- 12 examinations


def examinations_field(ctx: Context) -> ExaminationsField:
    docs = sorted(
        (d for d in ctx.docs.values() if d.type_code != LOINC_REFERRAL_NOTE), key=lambda d: (d.authored_at, d.doc_id)
    )
    if not docs:
        return _with_missing(
            ExaminationsField(status=HandoverStatus.MISSING), [_missing("examinations", Role.COORDINATOR)]
        )
    rows = [
        Examination(date=d.authored_at, place=d.custodian or NOT_STATED, type=d.title, doc_id=d.doc_id) for d in docs
    ]
    items = [HandoverItem(label=r.type, value=r.place, clinical_date=r.date) for r in rows]
    return ExaminationsField(
        status=HandoverStatus.COMPLETE, value=rows, items=items, note="Plné znění v odkazovaném dokumentu (doc_id)."
    )


# ---------------------------------------------------------------- 13 labs


def labs_field(ctx: Context) -> LabsField:
    numeric = [f for f in ctx.select([FactType.LAB_RESULT], fields=[13]) if (q := quantity(f)) and q.number is not None]
    reports = [f for f in numeric if ctx.doc_type(f) == LOINC_LAB_REPORT]
    # A value restated in a non-laboratory document (same test stem, same number) is already in the lab report.
    restated = [f for f in numeric if f not in reports and any(_same_result(f, r) for r in reports)]
    kept = [f for f in numeric if f not in restated]
    rows: dict[tuple[str, str, date, float], tuple[LabResult, Fact]] = {}
    for f in ctx.chronological(kept):
        q = quantity(f)
        assert q is not None  # noqa: S101 - filtered above
        assert q.number is not None  # noqa: S101
        row = LabResult(test=q.name, value=q.number, unit=f.unit, flag=q.flag, date=ctx.when(f), doc_id=f.doc_id)
        rows.setdefault((fold_text(q.name), f.unit or "", row.date, row.value), (row, f))
    if not rows:
        return _with_missing(LabsField(status=HandoverStatus.MISSING), [_missing("labs", Role.KOC_PHYSICIAN)])

    def order(key: tuple[str, str, date, float]) -> tuple[int, str, int, str]:
        name, unit, day, _ = key
        marker = next((i for i, m in enumerate(TUMOUR_MARKERS) if name == m), len(TUMOUR_MARKERS))
        return (marker, name, -day.toordinal(), unit)  # tumour markers first; per test the latest first

    ordered = [rows[k] for k in sorted(rows, key=order)]
    items = [
        make_item(
            ctx,
            row.value,
            [f],
            label=f"{row.test} ({f.specimen})" if f.specimen else row.test,
            unit=row.unit,
            clinical_date=row.date,
        )
        for row, f in ordered
    ]
    note = "U každého vyšetření nejdříve nejnovější hodnota, starší hodnoty ponechány."
    if any(f.specimen is None for _, f in ordered):
        note += " Materiál (krev/moč) není u výsledků uveden – rozlišení podle jednotky a citace."
    return LabsField(
        status=HandoverStatus.COMPLETE,
        value=[row for row, _ in ordered],
        items=items,
        evidence=union_evidence(f for _, f in ordered),
        note=note,
    )


def _same_result(a: Fact, b: Fact) -> bool:
    qa, qb = quantity(a), quantity(b)
    if qa is None or qb is None or qa.number != qb.number:
        return False
    return same_stem(qa.name.split()[0], qb.name.split()[0])


# ---------------------------------------------------------------- 14 histology


def histology_field(ctx: Context) -> HistologyField:
    pathology = [f for f in ctx.facts if ctx.doc_type(f) == LOINC_PATHOLOGY]
    histo = [f for f in ctx.facts if f.type == FactType.HISTOLOGY and f.handover_field in (3, 14)]
    facts = ctx.chronological({f.id: f for f in pathology + histo}.values())
    if not any(f.type == FactType.HISTOLOGY for f in facts):
        missing = [_missing("histology", Role.KOC_PHYSICIAN, "histologický nález v dokumentaci není")]
        return _with_missing(HistologyField(status=HandoverStatus.MISSING), missing)
    used: list[Fact] = []
    items: list[HandoverItem] = []
    report_id = None
    for f in facts:
        if (m := REPORT_ID.search(text_of(f))) is not None:
            report_id = m.group(0)
            used.append(f)
            items.append(make_item(ctx, report_id, [f], label="Číslo vyšetření"))
            break
    issued_fact = ctx.latest(
        f for f in facts if isinstance(v := value_of(f), DateValue) and "vydán" in v.label.casefold()
    )
    issued = None
    if issued_fact is not None:
        v = value_of(issued_fact)
        assert isinstance(v, DateValue)  # noqa: S101 - selected above
        issued = date.fromisoformat(v.date)
        used.append(issued_fact)
        items.append(make_item(ctx, cz_date(issued), [issued_fact], label="Datum vydání", clinical_date=issued))
    ihc: dict[str, str] = {}
    perineural: bool | None = None
    grade = None
    for f in facts:
        if f.type != FactType.HISTOLOGY:
            continue
        text = text_of(f)
        if (m := IHC.match(text)) and m.group(1).upper() == m.group(1) and (result := _ihc_result(m.group(2))):
            ihc[m.group(1)] = result
            used.append(f)
            items.append(make_item(ctx, m.group(2).strip(), [f], label=m.group(1)))
        if "perineurální invaz" in text.casefold():
            perineural = f.certainty != Certainty.NEGATED
            used.append(f)
            items.append(make_item(ctx, text, [f], label="Perineurální invaze"))
        if grade is None and (g := GRADE.search(text)):
            grade = g.group(0)
            used.append(f)
            items.append(make_item(ctx, grade, [f], label="Grading"))
    value = Histology(report_id=report_id, issued=issued, ihc=ihc, perineural_invasion=perineural, grade=grade)
    return HistologyField(status=HandoverStatus.COMPLETE, value=value, items=items, evidence=union_evidence(used))


def _ihc_result(text: str) -> str | None:
    t = text.strip().casefold()
    if t.startswith("pozitivn"):
        return "+"
    if t.startswith("negativn"):
        return "-"
    if t.startswith("exprese"):
        return text.strip()
    return None


# ---------------------------------------------------------------- 15 other


def other_field(ctx: Context, medications: Sequence[Medication] = ()) -> TextListField:
    """Consent and wishes first, then the living situation, then documented plans attributed to their document.

    Plans filed under medications are kept only when they name a listed drug (e.g. the apixaban pause), so a
    generic "Medikace beze změn." from an older report does not contradict the current list.
    """
    wishes = dedupe_by_text(ctx, ctx.select([FactType.CONSENT_OR_WISH], certainties=STATED))
    living = dedupe_by_text(
        ctx, [f for f in ctx.select([FactType.CONTACT], fields=[2]) if not isinstance(value_of(f), PersonValue)]
    )
    drugs = [m.drug for m in medications]
    plans = dedupe_by_text(
        ctx,
        [
            f
            for f in ctx.select([FactType.DOCUMENTED_PLAN], fields=[7, 15])
            if f.handover_field == 15 or any(_first_word_like(text_of(f), d) for d in drugs)
        ],
    )
    if not (wishes or living or plans):
        return _with_missing(TextListField(status=HandoverStatus.MISSING), [_missing("other", Role.COORDINATOR)])
    values = [text_of(f) for f in wishes + living] + [documented(ctx, f) for f in plans]
    items = [make_item(ctx, text_of(f), [f], label="Souhlas / přání", clinical_date=ctx.authored(f)) for f in wishes]
    items += [make_item(ctx, text_of(f), [f], label="Sociální situace", clinical_date=ctx.authored(f)) for f in living]
    items += [
        make_item(ctx, text_of(f), [f], label=f"{DOCUMENTED_PREFIX} ({ctx.docs[f.doc_id].title})",
                  clinical_date=ctx.authored(f))
        for f in plans
    ]  # fmt: skip
    return TextListField(
        status=HandoverStatus.COMPLETE, value=values, items=items, evidence=union_evidence(wishes + living + plans)
    )
