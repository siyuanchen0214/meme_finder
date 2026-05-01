from __future__ import annotations

import smtplib
from email.message import EmailMessage

from .config import EmailConfig


def send_email(cfg: EmailConfig, subject: str, body_markdown: str) -> None:
    msg = EmailMessage()
    msg["From"] = cfg.email_from
    msg["To"] = cfg.email_to
    msg["Subject"] = subject

    # Plain text is most compatible. (We can add HTML later.)
    msg.set_content(body_markdown)

    with smtplib.SMTP(cfg.smtp_host, cfg.smtp_port) as server:
        server.starttls()
        server.login(cfg.smtp_username, cfg.smtp_password)
        server.send_message(msg)

