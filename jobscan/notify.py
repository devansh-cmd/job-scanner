"""Sends the digest via Gmail SMTP using an app password.
Env: SMTP_USER (your Gmail), SMTP_PASS (16-letter app password), DIGEST_TO."""
from __future__ import annotations

import os
import smtplib
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText


def _clean(value: str) -> str:
    """Secrets pasted into GitHub often carry spaces or a trailing newline."""
    return "".join(value.split())


def send(subject: str, html: str) -> None:
    user = _clean(os.environ["SMTP_USER"])
    pw = _clean(os.environ["SMTP_PASS"])  # app passwords are shown with spaces
    to = _clean(os.environ.get("DIGEST_TO") or user)
    if len(pw) != 16:
        raise RuntimeError(f"SMTP_PASS should be a 16-letter Gmail app password, got {len(pw)} characters.")

    msg = MIMEMultipart("alternative")
    msg["Subject"], msg["From"], msg["To"] = subject, user, to
    msg.attach(MIMEText("Open in an HTML-capable mail client.", "plain"))
    msg.attach(MIMEText(html, "html"))
    try:
        with smtplib.SMTP_SSL("smtp.gmail.com", 465, timeout=30) as s:
            s.login(user, pw)
            s.sendmail(user, [to], msg.as_string())
    except (smtplib.SMTPAuthenticationError, smtplib.SMTPServerDisconnected) as e:
        raise RuntimeError(
            "Gmail rejected the login. Check: SMTP_USER is the exact Gmail address the app "
            "password was created on; SMTP_PASS is a current app password (not your normal "
            f"password); 2-Step Verification is on. Original error: {e}") from e
