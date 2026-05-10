"""Optional SMTP email to meeting participants (Notify Participants)."""

import asyncio
import smtplib
from email.mime.text import MIMEText
from email.utils import formataddr

from app.config import settings
from app.services.invite_recipients import filter_deliverable_invite_recipients


def _send_sync(to_addrs: list[str], subject: str, body: str) -> None:
    if not settings.smtp_host or not settings.smtp_from:
        raise RuntimeError("SMTP not configured")
    msg = MIMEText(body, "plain", "utf-8")
    msg["Subject"] = subject
    msg["From"] = (
        formataddr((settings.smtp_from_name, settings.smtp_from))
        if settings.smtp_from_name
        else settings.smtp_from
    )
    msg["To"] = settings.smtp_from
    msg["Bcc"] = ", ".join(to_addrs)
    with smtplib.SMTP(settings.smtp_host, settings.smtp_port, timeout=30) as server:
        if settings.smtp_use_tls:
            server.starttls()
        if settings.smtp_user:
            server.login(settings.smtp_user, settings.smtp_password or "")
        server.sendmail(settings.smtp_from, to_addrs, msg.as_string())


async def send_participant_digest(
    *,
    to_addrs: list[str],
    meeting_title: str,
    body_text: str,
) -> None:
    """Send one email per request (BCC all recipients in one message for simplicity)."""
    valid = filter_deliverable_invite_recipients(to_addrs)
    if not valid:
        return
    subject = f"Meeting update: {meeting_title}"
    await asyncio.to_thread(_send_sync, valid, subject, body_text)


def smtp_configured() -> bool:
    return bool(settings.smtp_host and settings.smtp_from)
