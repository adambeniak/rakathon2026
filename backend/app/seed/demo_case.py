"""The fictitious demo case (Alena Procházková, KOC 2 Nemocnice Lipová): directory, patient, case, documents.

Names, addresses and identifiers are copied from the fictitious documents in `data/raw/`. Values that the documents
do not state (e-mails, ECOG, TNM, …) are deliberately absent — the handover must report them as missing.
Received times are DEMO ASSUMPTIONS (the documents only state authored dates); they follow the story: the GP
attached nothing (finding D2), the coordinator requested reports 01–06, and 12–13 arrived after the MDT.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime
from typing import Final

from app.domain.case import CaseState
from app.domain.common import Role
from app.domain.directory import Organization, OrganizationKind, Practitioner, PractitionerRole
from app.domain.patient import Address, ContactPerson, Patient, Sex
from app.settings import PRAGUE

CASE_ID: Final = "rakathon-2026-prochazkova"
CASE_STATE: Final = CaseState.PRIPRAVENO_MDT
CASE_OPENED_AT: Final = datetime(2026, 10, 2, 9, 30, tzinfo=PRAGUE)
MDT_START: Final = datetime(2026, 10, 21, 8, 0, tzinfo=PRAGUE)

KOC2: Final = "koc2-nemocnice-lipova"
KOC1: Final = "koc1-nemocnice-severni"
GP_PRACTICE: Final = "pl-dolni-brezany"
INSURER: Final = "zp-211"

ORGANIZATIONS: Final = (
    Organization(
        id=GP_PRACTICE,
        name="Ordinace praktického lékaře – MUDr. Tomáš Řezníček",
        kind=OrganizationKind.GP_PRACTICE,
        address=Address(line="Na Návsi 3", postal_code="252 41", city="Dolní Břežany"),
        phone="+420 311 000 287",
        icp="72045318",
    ),
    Organization(
        id="kardio-jesenice",
        name="Kardiologická ambulance Jesenice",
        kind=OrganizationKind.OUTPATIENT,
        address=Address(line="Budějovická 410", postal_code="252 42", city="Jesenice"),
    ),
    Organization(
        id="labjih",
        name="Laboratoř LabJih s.r.o.",
        kind=OrganizationKind.LABORATORY,
        address=Address(line="Libušská 300", postal_code="142 00", city="Praha 4"),
    ),
    Organization(
        id="rc-modrany",
        name="Radiologické centrum Modřany",
        kind=OrganizationKind.IMAGING,
        address=Address(line="Komořanská 120", postal_code="143 00", city="Praha 4"),
    ),
    Organization(
        id="poliklinika-jizni",
        name="Poliklinika Jižní",
        kind=OrganizationKind.OUTPATIENT,
        address=Address(line="Za Poliklinikou 5", postal_code="143 00", city="Praha 4"),
    ),
    Organization(
        id=KOC1,
        name="KOC 1 – Nemocnice Severní",
        kind=OrganizationKind.KOC,
        address=Address(line="Severní 1200", postal_code="180 00", city="Praha 8"),
    ),
    Organization(
        id=KOC2,
        name="KOC 2 – Komplexní onkologické centrum Nemocnice Lipová",
        kind=OrganizationKind.KOC,
        address=Address(line="Nemocniční 15", postal_code="140 00", city="Praha 4"),
    ),
    Organization(
        id=INSURER,
        name="Zdravotní pojišťovna ministerstva vnitra ČR",
        kind=OrganizationKind.INSURER,
        insurer_code="211",
    ),
)


@dataclass(frozen=True)
class Person:
    practitioner: Practitioner
    role: PractitionerRole


def _person(
    slug: str,
    given: str,
    family: str,
    org: str,
    role: Role,
    specialty: str,
    *,
    prefix: tuple[str, ...] = ("MUDr.",),
    suffix: tuple[str, ...] = (),
) -> Person:
    return Person(
        Practitioner(id=slug, given=given, family=family, prefix=prefix, suffix=suffix),
        PractitionerRole(id=f"{slug}@{org}", practitioner_id=slug, organization_id=org, role=role, specialty=specialty),
    )


PEOPLE: Final = (
    _person("reznicek-tomas", "Tomáš", "Řezníček", GP_PRACTICE, Role.GP, "praktický lékař"),
    _person("maly-petr", "Petr", "Malý", "kardio-jesenice", Role.EXTERNAL_WORKPLACE, "kardiolog"),
    _person(
        "kolarova-hana",
        "Hana",
        "Kolářová",
        "labjih",
        Role.EXTERNAL_WORKPLACE,
        "odborný pracovník laboratoře",
        prefix=("RNDr.",),
    ),
    _person("hajkova-lucie", "Lucie", "Hájková", "rc-modrany", Role.EXTERNAL_WORKPLACE, "radiolog"),
    _person("krizova-ivana", "Ivana", "Křížová", "poliklinika-jizni", Role.EXTERNAL_WORKPLACE, "gastroenterolog"),
    _person("kopecky-jan", "Jan", "Kopecký", "poliklinika-jizni", Role.EXTERNAL_WORKPLACE, "radiolog"),
    _person("fiala-daniel", "Daniel", "Fiala", KOC1, Role.EXTERNAL_WORKPLACE, "radiolog", suffix=("Ph.D.",)),
    _person("holub-zdenek", "Zdeněk", "Holub", KOC1, Role.EXTERNAL_WORKPLACE, "algeziolog"),
    _person("dvorakova-lucie", "Lucie", "Dvořáková", KOC2, Role.COORDINATOR, "koordinátorka KOC", prefix=("Bc.",)),
    _person("svoboda-martin", "Martin", "Svoboda", KOC2, Role.KOC_PHYSICIAN, "gastroenterolog, endoskopista"),
    _person("markova-lenka", "Lenka", "Marková", KOC2, Role.KOC_PHYSICIAN, "klinická onkologie"),
    _person("pokorny-radek", "Radek", "Pokorný", KOC2, Role.KOC_PHYSICIAN, "patolog", suffix=("Ph.D.",)),
    _person(
        "hruby-pavel",
        "Pavel",
        "Hrubý",
        KOC2,
        Role.KOC_PHYSICIAN,
        "chirurg, HPB chirurgie; předseda MDT pro nádory GIT",
        prefix=("doc.", "MUDr."),
        suffix=("Ph.D.",),
    ),
    # Specialty kept exactly as listed in MDT_zapis (golden finding X3 is about this role).
    _person("kalous-ondrej", "Ondřej", "Kalous", KOC2, Role.KOC_PHYSICIAN, "radiační onkologie"),
    _person("simkova-eva", "Eva", "Šimková", KOC2, Role.KOC_PHYSICIAN, "radiologie"),
    _person(
        "sebestova-martina",
        "Martina",
        "Šebestová",
        KOC2,
        Role.KOC_STAFF,
        "odborný pracovník laboratoře",
        prefix=("Ing.",),
    ),
    _person("vesela-katerina", "Kateřina", "Veselá", KOC2, Role.KOC_STAFF, "klinický psycholog", prefix=("Mgr.",)),
)

GP_ROLE: Final = "reznicek-tomas@" + GP_PRACTICE
COORDINATOR_ROLE: Final = "dvorakova-lucie@" + KOC2
MDT_CHAIR_ROLE: Final = "hruby-pavel@" + KOC2
MDT_BATON_DISPLAY: Final = "MDT GIT – doc. MUDr. Pavel Hrubý, Ph.D."

PATIENT: Final = Patient(
    given="Alena",
    family="Procházková",
    sex=Sex.FEMALE,
    birth_date=date(1963, 7, 22),
    birth_number="635722/1013",
    insurer_code="211",
    phone="+420 777 000 541",
    address=Address(line="Za Školou 17", postal_code="252 41", city="Dolní Břežany"),
)
CONTACT_PERSON: Final = ContactPerson(name="Petra Horká", relation="dcera", phone="+420 777 000 542")


@dataclass(frozen=True)
class SeedDocument:
    file_name: str
    title: str
    loinc: str
    custodian: str
    author_role: str
    received_at: datetime

    @property
    def doc_id(self) -> str:
        return self.file_name.removesuffix(".docx")

    @property
    def authored_at(self) -> date:
        """Authored date parsed from the file name, e.g. '…_2026-10-19.docx'."""
        return date.fromisoformat(self.doc_id.rsplit("_", 1)[1])


def _at(month: int, day: int, hour: int, minute: int) -> datetime:
    return datetime(2026, month, day, hour, minute, tzinfo=PRAGUE)


CONSULT_NOTE, LAB_REPORT, IMAGING, REFERRAL_NOTE, PROCEDURE_NOTE, PATHOLOGY = (
    "11488-4",
    "11502-2",
    "18748-4",
    "57133-1",
    "28570-0",
    "11526-1",
)

DOCUMENTS: Final = (
    SeedDocument(
        "01_Kardiologie_2026-07-20.docx",
        "Kardiologie – ambulantní zpráva (kontrola)",
        CONSULT_NOTE,
        "kardio-jesenice",
        "maly-petr@kardio-jesenice",
        _at(10, 6, 9, 15),
    ),
    SeedDocument(
        "02_Laborator_2026-09-01.docx",
        "Laboratoř LabJih – výsledky",
        LAB_REPORT,
        "labjih",
        "kolarova-hana@labjih",
        _at(10, 6, 10, 40),
    ),
    SeedDocument(
        "03_RTG_plic_2026-09-03.docx",
        "RTG hrudníku PA",
        IMAGING,
        "rc-modrany",
        "hajkova-lucie@rc-modrany",
        _at(10, 6, 13, 20),
    ),
    SeedDocument(
        "04_PL_epikriza_2026-09-04.docx",
        "PL – epikríza a žádost o gastroenterologické vyšetření",
        REFERRAL_NOTE,
        GP_PRACTICE,
        GP_ROLE,
        _at(10, 5, 11, 0),
    ),
    SeedDocument(
        "05_Gastroenterologie_2026-09-15.docx",
        "Gastroenterologie – vstupní vyšetření",
        CONSULT_NOTE,
        "poliklinika-jizni",
        "krizova-ivana@poliklinika-jizni",
        _at(10, 7, 8, 50),
    ),
    SeedDocument(
        "06_UZ_bricha_2026-09-29.docx",
        "UZ břicha",
        IMAGING,
        "poliklinika-jizni",
        "kopecky-jan@poliklinika-jizni",
        _at(10, 7, 14, 5),
    ),
    SeedDocument(
        "07_PL_zadost_KOC2_2026-10-02.docx",
        "PL – epikríza a žádost o převzetí do péče KOC",
        REFERRAL_NOTE,
        GP_PRACTICE,
        GP_ROLE,
        _at(10, 2, 9, 30),
    ),
    SeedDocument(
        "08_CT_KOC1_2026-10-08.docx",
        "CT břicha a hrudníku – pankreatický protokol (KOC 1)",
        IMAGING,
        KOC1,
        "fiala-daniel@" + KOC1,
        _at(10, 8, 15, 30),
    ),
    SeedDocument(
        "09_Biopsie_vykon_KOC2_2026-10-12.docx",
        "EUS-FNB – protokol o výkonu (KOC 2)",
        PROCEDURE_NOTE,
        KOC2,
        "svoboda-martin@" + KOC2,
        _at(10, 12, 13, 0),
    ),
    SeedDocument(
        "10_Laborator_KOC2_2026-10-15.docx",
        "Laboratoř KOC 2 – výsledky",
        LAB_REPORT,
        KOC2,
        "sebestova-martina@" + KOC2,
        _at(10, 15, 14, 0),
    ),
    SeedDocument(
        "11_Histologie_KOC2_2026-10-19.docx",
        "Histologie – bioptický nález (KOC 2)",
        PATHOLOGY,
        KOC2,
        "pokorny-radek@" + KOC2,
        _at(10, 19, 16, 0),
    ),
    SeedDocument(
        "12_Algeziologie_2026-10-26.docx",
        "Algeziologie – ambulantní zpráva (KOC 1)",
        CONSULT_NOTE,
        KOC1,
        "holub-zdenek@" + KOC1,
        _at(10, 26, 12, 0),
    ),
    SeedDocument(
        "13_Psychologie_KOC2_2026-10-27.docx",
        "Psychoonkologie – zpráva klinického psychologa (KOC 2)",
        CONSULT_NOTE,
        KOC2,
        "vesela-katerina@" + KOC2,
        _at(10, 27, 15, 0),
    ),
)
