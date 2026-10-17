"""The e-mail that tells the referring GP that the MDT feedback is waiting in the portal.

Data minimisation: the body carries NO clinical content (no patient name, diagnosis, conclusion or case id) —
only who sends it, the MDT date and a link to the GP portal, where the GP signs in and reads the feedback.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

from app.domain.directory import PractitionerRole
from app.notify.mailer import MailMessage
from app.settings import Settings

SENDER_NAME = "Štafeta"
SENDER_ADDRESS = "stafeta@demo.stafeta.example"
DEFAULT_PORTAL_ORIGIN = "http://localhost:5173"
PORTAL_PATH = "/gp"
SUBJECT = "Štafeta: zpětná vazba z MDT je k dispozici"
BODY = """Dobrý den,

{koc} Vám zasílá zpětnou vazbu z multioborového semináře (MDT){mdt_date}.

Zpětná vazba je k dispozici v portálu Štafeta: {portal_url}

Obsah zprávy záměrně neuvádíme e-mailem. Do portálu se přihlaste svým účtem.

Kontakt na koordinátora: {coordinator}

Toto je automatická zpráva ze systému Štafeta (prototyp, fiktivní data). Na tuto zprávu neodpovídejte.
"""


def portal_url(settings: Settings) -> str:
    """The GP portal of the first configured frontend origin (CORS origins are explicit outside local)."""
    origin = next((o for o in settings.cors_origins if o.startswith(("http://", "https://"))), DEFAULT_PORTAL_ORIGIN)
    return origin.rstrip("/") + PORTAL_PATH


def demo_mailbox(role: PractitionerRole) -> str:
    """A fictitious mailbox derived from the role id, until the directory carries real addresses.

    The seed deliberately holds no e-mail addresses (the source documents state none); the demo relay accepts any.
    """
    local = f"{role.practitioner_id}.{role.organization_id}"
    return f"{local}@demo.stafeta.example"


@dataclass(frozen=True)
class FeedbackMailInput:
    recipient: PractitionerRole
    koc_name: str
    coordinator_display: str
    portal_url: str
    mdt_start: datetime | None


def build_feedback_mail(data: FeedbackMailInput, *, message_id: str) -> MailMessage:
    mdt_date = f" konaného {data.mdt_start.strftime('%-d. %-m. %Y')}" if data.mdt_start else ""
    body = BODY.format(
        koc=data.koc_name, mdt_date=mdt_date, portal_url=data.portal_url, coordinator=data.coordinator_display
    )
    return MailMessage(
        sender_name=SENDER_NAME,
        sender_address=SENDER_ADDRESS,
        recipient_address=demo_mailbox(data.recipient),
        subject=SUBJECT,
        body=body,
        message_id=message_id,
    )
