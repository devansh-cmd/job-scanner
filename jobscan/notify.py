"""Sends the digest via Gmail SMTP using an app password.
Env: SMTP_USER (your Gmail), SMTP_PASS (16-char app password), DIGEST_TO."""
from __future__ import annotations

import os
import smtplib
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText


def send(subject: str, html: str) -> None:
    user, pw = os.environ["SMTP_USER"], os.environ["SMTP_PASS"]
    to = os.environ.get("DIGEST_TO", user)
    msg = MIMEMultipart("alternative")
    msg["Subject"], msg["From"], msg["To"] = subject, user, to
    msg.attach(MIMEText("Open in an HTML-capable mail client.", "plain"))
    msg.attach(MIMEText(html, "html"))
    with smtplib.SMTP_SSL("smtp.gmail.com", 465, timeout=30) as s:
        s.login(user, pw)
        s.sendmail(user, [to], msg.as_string())
