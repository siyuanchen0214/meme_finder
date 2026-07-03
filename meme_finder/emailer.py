from __future__ import annotations

import smtplib
from email.message import EmailMessage
from typing import Optional

from .config import EmailConfig
from .render import markdown_to_email_html


def send_email(
    cfg: EmailConfig,
    subject: str,
    body_markdown: str,
    *,
    html: Optional[str] = None,
) -> None:
    msg = EmailMessage()
    msg["From"] = cfg.email_from
    msg["To"] = cfg.email_to
    msg["Subject"] = subject

    # Plain text as the fallback part (raw markdown).
    msg.set_content(body_markdown)

    # HTML alternative so clients render headings/bold/links nicely.
    if html is None:
        html = markdown_to_email_html(body_markdown, title=subject)
    msg.add_alternative(html, subtype="html")

    with smtplib.SMTP(cfg.smtp_host, cfg.smtp_port) as server:
        server.starttls()
        server.login(cfg.smtp_username, cfg.smtp_password)
        server.send_message(msg)
