"""Write to Alex: a visitor's own email, handled live.

The recorded morning shows one fixed week. This lets a judge send Alex a message of their own,
from a client, a late payer or a stranger, and watch Kept handle just that email on the real
models: sort it, check it against the signed agreement, pull out the promises in both
directions, and react if the client is delighted. One email takes a handful of calls, so the
answer comes back in seconds rather than minutes. Nothing is ever sent; drafts wait for Yes.
"""
from __future__ import annotations

import re
import time
import uuid
from datetime import date

from . import approvals, ledger
from .store import locked, now_iso, read_audit, read_json, write_json

# who a visitor can write as, and what Kept knows about each of them in the demo week
PEOPLE = [
    {"key": "maria", "name": "Maria Lopez", "email": "maria@sunrisebakery.example",
     "about": "client, Sunrise Bakery site in progress, signed agreement"},
    {"key": "jordan", "name": "Jordan Kim", "email": "jordan@kimyoga.example",
     "about": "client, Kim Yoga site, signed agreement"},
    {"key": "priya", "name": "Priya Shah", "email": "priya@shahdental.example",
     "about": "client, usually pays about 12 days late; invoice #118 ($850) is overdue"},
    {"key": "lucia", "name": "Lucia Ferri", "email": "lucia@ferriboutique.example",
     "about": "past client, paid early, boutique"},
    {"key": "noah", "name": "Noah Brooks", "email": "noah@brookscoffee.example",
     "about": "client, Brooks Coffee site just launched"},
    {"key": "dev", "name": "Dev Patel", "email": "dev@greenleaflandscaping.example",
     "about": "lead, asked for rates"},
]
MAX_BODY = 2000


def people() -> list[dict]:
    return PEOPLE


def client_base() -> list[dict]:
    """Everyone Alex deals with in the demo, with what Kept knows about each. People a visitor
    invents by writing in are added here too: Kept remembers them like any other contact."""
    from .agent import sender
    from .reply import facts_about, thread
    from .tools import mail

    rows = [dict(p) for p in PEOPLE]
    known = {p["email"] for p in rows}
    for m in mail.inbox(500):
        name, addr = sender(m)
        if m["id"].startswith("you:") and addr not in known:
            rows.append({"key": "new", "name": name, "email": addr, "about": "new contact who wrote in through this demo"})
            known.add(addr)
    for p in rows:
        t = thread(p["email"])
        p["facts"] = facts_about(p["email"], p["name"])
        p["messages"] = len([x for x in t if x["dir"] in ("in", "out")])
        p["drafts"] = len([x for x in t if x["dir"] == "draft"])
        p["last"] = t[-1]["ts"] if t else None
    return rows


def _sender(key: str, name: str, email: str) -> tuple[str, str]:
    p = next((p for p in PEOPLE if p["key"] == key), None)
    if p:
        return p["name"], p["email"]
    name = re.sub(r"[<>\"\n\r]", "", (name or "").strip())[:60] or "New contact"
    email = (email or "").strip().lower()[:120]
    if not re.fullmatch(r"[^@\s<>]+@[^@\s<>]+\.[a-z]{2,}", email):
        raise ValueError("Give the new contact an email address like jo@example.com")
    return name, email


def handle(key: str, subject: str, body: str, name: str = "", email: str = "") -> dict:
    from . import growth
    from .agent import _triage_one
    from .reply import thread

    body = (body or "").strip()
    if len(body) < 10:
        raise ValueError("Write a few words, at least a sentence")
    body = body[:MAX_BODY]
    subject = (subject or "").strip()[:120] or "(no subject)"
    who, addr = _sender(key, name, email)
    m = {"id": f"you:{uuid.uuid4().hex[:6]}", "from": f"{who} <{addr}>", "subject": subject,
         "date": date.today().isoformat(), "ts": now_iso(), "body": body}

    t0 = time.time()
    audit_before = len(read_audit(100000))
    approvals_before = {a["id"] for a in approvals.recent(10000)}
    abstained_before = len(read_json("abstained.json", []))
    with locked():
        inbox = read_json("inbox.json", [])
        inbox.append(m)
        write_json("inbox.json", inbox)

    one = _triage_one(m)
    with locked():
        seen = set(read_json("seen_mail.json", []))
        seen.add(m["id"])
        write_json("seen_mail.json", sorted(seen))
        if one["cls"]:
            labels = read_json("labels.json", {})
            labels[m["id"]] = one["cls"]
            write_json("labels.json", labels)

    growth_out = None
    if one["cls"] and one["cls"].get("kind") == "client":
        growth_out = growth.moments(only=[m])
    reply_out = None
    label = one["cls"] or {}
    if label and label.get("kind") != "noise" and not (growth_out or {}).get("asks"):
        # a delighted client already gets the thank-you (with the review link) from growth
        from .reply import draft_reply
        reply_out = draft_reply(m, label, one["scope"])

    calls = [a for a in read_audit(100000)[audit_before:] if a.get("kind") == "llm"]
    new_approvals = [a for a in approvals.recent(10000) if a["id"] not in approvals_before]
    held = read_json("abstained.json", [])[abstained_before:]
    skipped = [a for a in read_audit(100000)[audit_before:] if a.get("kind") == "approval_skipped"]
    return {
        "mail": m,
        "label": one["cls"],
        "scope": one["scope"],
        "promises": [{**r, "already_known": r.get("source") != m["id"]} for r in one["commitments"]],
        "approvals": new_approvals,
        "growth": growth_out,
        "reply": {k: v for k, v in (reply_out or {}).items() if k != "held"} if reply_out else None,
        "held_back": [{"job": h["job"], "subject": h["subject"], "problems": h["problems"]} for h in held],
        "waiting_already": [s.get("waiting") for s in skipped],
        "calls": [{"tier": c["tier"], "purpose": c["purpose"], "ms": c["ms"]} for c in calls],
        "usd": round(sum(c["usd"] for c in calls), 4),
        "seconds": round(time.time() - t0, 1),
        "thread": thread(addr),
    }
