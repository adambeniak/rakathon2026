"""Outgoing e-mail: a small port (`Mailer`) and the SMTP adapter used with Mailpit (demo).

The adapter speaks plain SMTP (no STARTTLS, no authentication): fine for the loopback/compose Mailpit, NOT for a real
relay (issue #77). The returned receipt means "the relay accepted the message", not that the recipient got or read it.

The message id is chosen by the caller before sending, so it can be recorded as the delivery receipt
(`Communication.identifier`, `delivery_confirmed.receipt_id`). Nothing here logs addresses or bodies.
"""

from __future__ import annotations

import asyncio
import smtplib
from dataclasses import dataclass
from email.message import EmailMessage
from email.utils import formataddr, make_msgid
from typing import Protocol

import structlog

from app.domain.errors import ServiceUnavailableError

log = structlog.get_logger(__name__)

MESSAGE_ID_DOMAIN = "stafeta.example"
SMTP_TIMEOUT_S = 10.0


class MailDeliveryError(ServiceUnavailableError):
    """The relay refused or could not be reached. Nothing was delivered; the caller may retry."""

    def __init__(self) -> None:
        super().__init__("mail-unavailable", "E-mail se nepodařilo odeslat; zkuste to znovu.")


@dataclass(frozen=True)
class MailMessage:
    sender_name: str
    sender_address: str
    recipient_address: str
    subject: str
    body: str
    message_id: str


def new_message_id() -> str:
    """RFC 5322 Message-ID including the angle brackets, e.g. '<2026...@stafeta.example>'."""
    return make_msgid(domain=MESSAGE_ID_DOMAIN)


class Mailer(Protocol):
    async def send(self, message: MailMessage) -> str:
        """Hand the message to the relay and return its Message-ID; raise `MailDeliveryError` otherwise."""
        ...


def to_email(message: MailMessage) -> EmailMessage:
    email = EmailMessage()
    email["From"] = formataddr((message.sender_name, message.sender_address))
    email["To"] = message.recipient_address
    email["Subject"] = message.subject
    email["Message-ID"] = message.message_id
    email.set_content(message.body, charset="utf-8")
    return email


class SmtpMailer:
    """Plain SMTP without authentication or TLS: the demo relay is Mailpit on the compose network."""

    def __init__(self, host: str, port: int, *, timeout: float = SMTP_TIMEOUT_S) -> None:
        self._host = host
        self._port = port
        self._timeout = timeout

    async def send(self, message: MailMessage) -> str:
        try:
            email = to_email(message)  # the header policy refuses control characters in any header value
            await asyncio.to_thread(self._deliver, email, message.recipient_address)
        except (OSError, ValueError, smtplib.SMTPException) as exc:
            log.warning("mail_delivery_failed", error=type(exc).__name__, message_id=message.message_id)
            raise MailDeliveryError from exc
        return message.message_id

    def _deliver(self, email: EmailMessage, recipient: str) -> None:
        with smtplib.SMTP(self._host, self._port, timeout=self._timeout) as smtp:
            smtp.send_message(email, to_addrs=[recipient])  # explicit envelope recipient, not parsed from headers
