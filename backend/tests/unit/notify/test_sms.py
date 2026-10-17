"""Demo SMS gateway: an SMS becomes an e-mail to <digits>@sms.demo.stafeta.example; bad numbers are refused."""

from __future__ import annotations

import pytest

from app.notify.mailer import MailMessage, to_email
from app.notify.sms import InvalidPhoneError, MailpitSmsGateway, SmsMessage, sms_address


class CapturingMailer:
    def __init__(self) -> None:
        self.sent: list[MailMessage] = []

    async def send(self, message: MailMessage) -> str:
        self.sent.append(message)
        return message.message_id


async def test_sms_is_delivered_as_mail_to_the_number_mailbox() -> None:
    mailer = CapturingMailer()

    receipt = await MailpitSmsGateway(mailer).send(SmsMessage(phone="+420 777 000 541", body="Štafeta: text"))

    (mail,) = mailer.sent
    assert receipt == mail.message_id
    assert mail.recipient_address == "420777000541@sms.demo.stafeta.example"
    assert mail.subject == "SMS · +420 777 000 541"
    assert mail.sender_name == "Štafeta SMS"
    assert mail.body == "Štafeta: text"
    email = to_email(mail)  # the real header policy accepts it
    assert email["To"] == "420777000541@sms.demo.stafeta.example"


@pytest.mark.parametrize(
    "phone",
    ["+420 777\r\nBcc: x@example.org", "+420 777 000 541\n", "777-000-541", "x@example.org", "", "+"],
)
async def test_header_injection_and_non_numbers_are_refused(phone: str) -> None:
    mailer = CapturingMailer()
    with pytest.raises(InvalidPhoneError):
        await MailpitSmsGateway(mailer).send(SmsMessage(phone=phone, body="x"))
    assert mailer.sent == []


def test_address_normalises_spacing() -> None:
    assert sms_address("+420  777 000   541") == "420777000541@sms.demo.stafeta.example"
    assert sms_address("777000541") == "777000541@sms.demo.stafeta.example"
