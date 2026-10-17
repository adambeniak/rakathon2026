"""Outgoing SMS: a small port (`SmsGateway`) and the demo adapter that delivers into Mailpit.

There is no real SMS operator in the prototype. `MailpitSmsGateway` hands each SMS to the mail relay as an e-mail to
`<digits>@sms.demo.stafeta.example`, so the demo shows it in the Mailpit inbox. The returned id is the relay's
Message-ID ("accepted for delivery", not "read by the patient"). Nothing here logs the phone number or the text.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Final, Protocol

from app.notify.mailer import MailDeliveryError, Mailer, MailMessage, new_message_id

SMS_DOMAIN: Final = "sms.demo.stafeta.example"
SENDER_NAME: Final = "Štafeta SMS"
SENDER_ADDRESS: Final = "sms@demo.stafeta.example"
SUBJECT: Final = "SMS · {phone}"
# International or national format with optional single spaces: '+420 777 000 541', '777000541'.
_PHONE: Final = re.compile(r"^\+?[0-9]{1,4}(?: ?[0-9]{2,4}){1,5}$")

SmsDeliveryError = MailDeliveryError  # the demo gateway fails exactly when the relay does


class InvalidPhoneError(ValueError):
    """The stored number is not a plain phone number (and would not be safe in an address or header)."""


@dataclass(frozen=True)
class SmsMessage:
    phone: str
    body: str


def normalized_phone(phone: str) -> str:
    """The number with single spaces, or `InvalidPhoneError` (this also rejects CR/LF header injection)."""
    candidate = " ".join(phone.split()) if "\r" not in phone and "\n" not in phone else phone
    if not _PHONE.fullmatch(candidate):
        raise InvalidPhoneError("not a phone number")
    return candidate


def sms_address(phone: str) -> str:
    """'+420 777 000 541' -> '420777000541@sms.demo.stafeta.example'."""
    return f"{re.sub(r'[^0-9]', '', normalized_phone(phone))}@{SMS_DOMAIN}"


class SmsGateway(Protocol):
    async def send(self, message: SmsMessage) -> str:
        """Hand the SMS to the operator and return its message id; raise `SmsDeliveryError` otherwise."""
        ...


class MailpitSmsGateway:
    """Demo only: every SMS becomes an e-mail in Mailpit."""

    def __init__(self, mailer: Mailer) -> None:
        self._mailer = mailer

    async def send(self, message: SmsMessage) -> str:
        phone = normalized_phone(message.phone)
        mail = MailMessage(
            sender_name=SENDER_NAME,
            sender_address=SENDER_ADDRESS,
            recipient_address=sms_address(phone),
            subject=SUBJECT.format(phone=phone),
            body=message.body,
            message_id=new_message_id(),
        )
        return await self._mailer.send(mail)
