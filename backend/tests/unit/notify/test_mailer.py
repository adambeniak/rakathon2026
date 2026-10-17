"""SmtpMailer against a real (in-process) SMTP server, and the minimisation of the feedback e-mail."""

from __future__ import annotations

import socket
import socketserver
import threading
from collections.abc import Iterator
from datetime import datetime
from email import message_from_bytes
from email.message import Message

import pytest

from app.notify.feedback_mail import (
    FeedbackMailInput,
    build_feedback_mail,
    demo_mailbox,
    portal_url,
)
from app.notify.mailer import MailDeliveryError, MailMessage, SmtpMailer, new_message_id
from app.seed import demo_case
from app.settings import PRAGUE, Settings
from tests.directory_fixtures import demo_directory

MDT_START = datetime(2026, 10, 21, 8, 0, tzinfo=PRAGUE)
GP = demo_directory().role(demo_case.GP_ROLE)
assert GP


class _Handler(socketserver.StreamRequestHandler):
    """Just enough SMTP for smtplib: EHLO, MAIL, RCPT, DATA, QUIT."""

    def handle(self) -> None:
        server: _Server = self.server  # type: ignore[assignment]
        self._say("220 test ESMTP")
        data_lines: list[bytes] | None = None
        while line := self.rfile.readline():
            if data_lines is not None:
                if line.rstrip(b"\r\n") == b".":
                    server.received.append(b"".join(data_lines))
                    data_lines = None
                    self._say("554 rejected" if server.reject else "250 queued")
                else:
                    data_lines.append(line)
                continue
            command = line.decode("ascii", "replace").strip().upper()
            if command.startswith("DATA"):
                data_lines = []
                self._say("354 go ahead")
            elif command.startswith("QUIT"):
                self._say("221 bye")
                return
            else:
                self._say("250 ok")

    def _say(self, text: str) -> None:
        self.wfile.write(text.encode("ascii") + b"\r\n")
        self.wfile.flush()


class _Server(socketserver.ThreadingTCPServer):
    allow_reuse_address = True
    daemon_threads = True

    def __init__(self) -> None:
        super().__init__(("127.0.0.1", 0), _Handler)
        self.received: list[bytes] = []
        self.reject = False


@pytest.fixture
def smtp_server() -> Iterator[_Server]:
    server = _Server()
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    yield server
    server.shutdown()
    server.server_close()


def _message(body: str = "Dobrý den, zpráva s diakritikou: čřž.") -> MailMessage:
    return MailMessage(
        sender_name="Štafeta",
        sender_address="stafeta@demo.stafeta.example",
        recipient_address="gp@demo.stafeta.example",
        subject="Štafeta: zpětná vazba z MDT je k dispozici",
        body=body,
        message_id=new_message_id(),
    )


async def test_smtp_mailer_delivers_utf8_and_returns_the_message_id(smtp_server: _Server) -> None:
    mailer = SmtpMailer("127.0.0.1", smtp_server.server_address[1])
    message = _message()

    receipt = await mailer.send(message)

    assert receipt == message.message_id
    [raw] = smtp_server.received
    parsed: Message = message_from_bytes(raw)
    assert parsed["Message-ID"] == message.message_id
    assert parsed["To"] == "gp@demo.stafeta.example"
    payload = parsed.get_payload(decode=True)
    assert isinstance(payload, bytes)
    assert "čřž" in payload.decode("utf-8")


async def test_smtp_mailer_raises_when_the_relay_rejects(smtp_server: _Server) -> None:
    smtp_server.reject = True
    mailer = SmtpMailer("127.0.0.1", smtp_server.server_address[1])

    with pytest.raises(MailDeliveryError):
        await mailer.send(_message())


async def test_smtp_mailer_raises_when_nobody_listens() -> None:
    with socket.socket() as probe:
        probe.bind(("127.0.0.1", 0))
        port = probe.getsockname()[1]  # closed again on exit: connection refused

    with pytest.raises(MailDeliveryError):
        await SmtpMailer("127.0.0.1", port, timeout=2).send(_message())


def test_feedback_mail_holds_no_clinical_content() -> None:
    mail = build_feedback_mail(
        FeedbackMailInput(
            recipient=GP.role,
            koc_name="KOC 2 – Komplexní onkologické centrum Nemocnice Lipová",
            coordinator_display="Bc. Lucie Dvořáková",
            portal_url="http://localhost:5173/gp",
            mdt_start=MDT_START,
        ),
        message_id="<m1@stafeta.example>",
    )

    assert mail.recipient_address == demo_mailbox(GP.role)
    assert "http://localhost:5173/gp" in mail.body
    assert "21. 10. 2026" in mail.body
    text = f"{mail.subject}\n{mail.body}".lower()
    for forbidden in ("alena", "procházk", "rakathon", "pankreat", "karcinom", "c25", "635722", "závěr mdt:"):
        assert forbidden not in text, forbidden


def test_portal_url_follows_the_first_http_origin(settings: Settings) -> None:
    deployed = settings.model_copy(update={"cors_origins": ["https://stafeta.example/", "http://localhost:5173"]})

    assert portal_url(deployed) == "https://stafeta.example/gp"
    assert portal_url(settings.model_copy(update={"cors_origins": ["*"]})) == "http://localhost:5173/gp"
