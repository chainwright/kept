"""Mail in and out.

Inbox: real IMAP if configured, otherwise the demo inbox in data/inbox.json.
Outbox: sending is a guarded action. In demo mode the message is written to
data/outbox/ instead of leaving the machine, so pressing Yes is always safe.
"""
from __future__ import annotations

import email
import imaplib
import json
import smtplib
from email.header import decode_header
from email.mime.text import MIMEText
from pathlib import Path

from ..approvals import action
from ..config import settings
from ..store import data_dir, now_iso


def _decode(h: str | None) -> str:
    if not h:
        return ""
    return "".join(p.decode(c or "utf-8", "ignore") if isinstance(p, bytes) else p
                   for p, c in decode_header(h))


def inbox(limit: int = 20) -> list[dict]:
    """[{id, from, subject, date, body}] newest last."""
    demo = data_dir() / "inbox.json"
    if settings.demo or not settings.smtp_host:
        return json.loads(demo.read_text())[-limit:] if demo.exists() else []
    m = imaplib.IMAP4_SSL(settings.smtp_host.replace("smtp.", "imap."))
    m.login(settings.smtp_user, settings.smtp_password)
    m.select("INBOX", readonly=True)
    _, data = m.search(None, "ALL")
    out = []
    for num in data[0].split()[-limit:]:
        _, raw = m.fetch(num, "(BODY.PEEK[])")
        msg = email.message_from_bytes(raw[0][1])
        body = ""
        for part in msg.walk():
            if part.get_content_type() == "text/plain" and part.get_payload(decode=True):
                body = part.get_payload(decode=True).decode("utf-8", "ignore")
                break
        out.append({"id": f"mail:{num.decode()}", "from": _decode(msg["From"]),
                    "subject": _decode(msg["Subject"]), "date": msg["Date"], "body": body[:6000]})
    m.logout()
    return out


@action("send_email", needs_approval=True)
def send_email(args: dict) -> str:
    to, subject, body = args["to"], args["subject"], args["body"]
    if settings.demo or not settings.smtp_host:
        out = data_dir() / "outbox" / f"{now_iso().replace(':', '-')}_{to.split('@')[0]}.json"
        out.write_text(json.dumps({"to": to, "subject": subject, "body": body, "ts": now_iso(),
                                   "note": "demo mode: written to outbox, not sent"}, indent=1))
        return f"demo: saved to outbox/{out.name}"
    msg = MIMEText(body)
    msg["From"], msg["To"], msg["Subject"] = settings.smtp_user, to, subject
    with smtplib.SMTP_SSL(settings.smtp_host, 465) as s:
        s.login(settings.smtp_user, settings.smtp_password)
        s.sendmail(settings.smtp_user, [to], msg.as_string())
    return f"sent to {to}"
