"""Write to Alex: a visitor's own email (and photo), handled live.

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
from .store import data_dir, locked, now_iso, read_audit, read_json, write_json

# who a visitor can write as, and what Kept knows about each of them in the demo week
PEOPLE = [
    {"key": "maria", "name": "Maria Lopez", "email": "maria@lopezhome.example",
     "about": "homeowner; Alex is remodelling her kitchen right now under a signed agreement"},
    {"key": "jordan", "name": "Jordan Kim", "email": "jordan@kimfamily.example",
     "about": "homeowner; new cabinet fronts and countertop finished, 60-day fix guarantee"},
    {"key": "priya", "name": "Priya Shah", "email": "priya@shahdental.example",
     "about": "dental office; usually pays about 12 days late; invoice #118 ($850) is overdue"},
    {"key": "lucia", "name": "Lucia Ferri", "email": "lucia@ferriboutique.example",
     "about": "boutique owner; Alex built her staff kitchenette, she paid early"},
    {"key": "noah", "name": "Noah Brooks", "email": "noah@brookscoffee.example",
     "about": "Brooks Coffee; Alex just rebuilt the back counter and shelves"},
    {"key": "dev", "name": "Dev Patel", "email": "dev@patelfamily.example",
     "about": "new lead; bought a 1950s house and wants the kitchen redone"},
]
MAX_BODY = 2000


def people() -> list[dict]:
    return PEOPLE


def client_base() -> list[dict]:
    """Everyone Alex deals with in the demo, with what Kept knows about each. People a visitor
    invents by writing in are added here too: Kept remembers them like any other contact."""
    from .agent import sender
    from . import research
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
        p["web"] = research.known(p["email"])
        p["messages"] = len([x for x in t if x["dir"] in ("in", "out")])
        p["drafts"] = len([x for x in t if x["dir"] == "draft"])
        p["last"] = t[-1]["ts"] if t else None
    return rows


def _save_photo(mid: str, image: str):
    """A data: URL from the browser, at most ~4 MB, jpeg/png/webp only."""
    import base64
    from pathlib import Path
    m = re.match(r"data:image/(jpeg|jpg|png|webp);base64,(.+)$", image or "", re.S)
    if not m:
        raise ValueError("The photo must be a JPEG, PNG or WebP image")
    raw = base64.b64decode(m.group(2))
    if len(raw) > 4_500_000:
        raise ValueError("That photo is too large; under 4 MB, please")
    d = data_dir() / "media" / "inbox"
    d.mkdir(parents=True, exist_ok=True)
    p = d / f"{mid.replace(':', '-')}.{'jpg' if m.group(1) in ('jpeg', 'jpg') else m.group(1)}"
    p.write_bytes(raw)
    return Path(p)


def remember(addr: str, who: str, before: list[dict]) -> dict | None:
    """What Kept already knows about this person from earlier messages: when they first wrote and about
    what, the estimate Kept worked out, a visit booked. All of it read from Alex's records, none of it guessed."""
    from . import estimate, schedule
    prior = [t for t in before if t["dir"] in ("in", "out")]
    if not prior:
        return None
    first_in = next((t for t in prior if t["dir"] == "in"), prior[0])
    last = prior[-1]["ts"][:10]
    out = {"since": first_in["ts"][:10], "topic": first_in["subject"], "messages": len(prior), "last": last,
           "days": max(0, (date.today() - date.fromisoformat(last)).days)}
    est = estimate.last_for(addr)
    if est and est.get("low"):
        out["estimate"] = {"low": int(est["low"]), "high": int(est["high"]), "job": est.get("job", "")}
    visit = next((e for e in schedule.upcoming(60) if e.get("contact") == addr.lower()), None)
    if visit:
        out["visit"] = f"{date.fromisoformat(visit['date']):%a %b %-d} at {schedule.clock(visit['time'])}"
    return out


def same_name_elsewhere(addr: str, who: str) -> dict | None:
    """A new address with the name of someone Alex already knows. Names repeat, so Kept never merges them
    on its own; it tells Alex, who can tell the two apart."""
    from .agent import sender
    from .tools import mail
    key = who.strip().lower()
    if not key or key == "new contact":
        return None
    for p in PEOPLE:
        if p["name"].lower() == key and p["email"] != addr:
            return {"name": p["name"], "email": p["email"], "about": p["about"]}
    for m in mail.inbox(500):
        n, a = sender(m)
        if n.strip().lower() == key and a != addr:
            return {"name": n, "email": a, "about": f"wrote on {str(m.get('date'))[:10]} about '{m['subject']}'"}
    return None


def _sender(key: str, name: str, email: str) -> tuple[str, str]:
    p = next((p for p in PEOPLE if p["key"] == key), None)
    if p:
        return p["name"], p["email"]
    name = re.sub(r"[<>\"\n\r]", "", (name or "").strip())[:60] or "New contact"
    email = (email or "").strip().lower()[:120]
    if not re.fullmatch(r"[^@\s<>]+@[^@\s<>]+\.[a-z]{2,}", email):
        raise ValueError("Give the new contact an email address like jo@example.com")
    return name, email


def handle(key: str, subject: str, body: str, name: str = "", email: str = "", image: str = "") -> dict:
    from . import growth
    from .agent import _triage_one
    from .reply import thread

    body = (body or "").strip()
    if len(body) < 10:
        raise ValueError("Write a few words, at least a sentence")
    body = body[:MAX_BODY]
    subject = (subject or "").strip()[:120] or "(no subject)"
    who, addr = _sender(key, name, email)
    memory = remember(addr, who, thread(addr))
    lookalike = None if memory else same_name_elsewhere(addr, who)
    m = {"id": f"you:{uuid.uuid4().hex[:6]}", "from": f"{who} <{addr}>", "subject": subject,
         "date": date.today().isoformat(), "ts": now_iso(), "body": body}

    t0 = time.time()
    audit_before = len(read_audit(100000))
    approvals_before = {a["id"] for a in approvals.recent(10000)}
    abstained_before = len(read_json("abstained.json", []))
    # the photo is checked and saved before anything is written, so a bad file leaves no half-email behind
    photo_path = _save_photo(m["id"], image) if image else None
    if photo_path:
        m["photo"] = str(photo_path.relative_to(data_dir()))
    with locked():
        inbox = read_json("inbox.json", [])
        inbox.append(m)
        write_json("inbox.json", inbox)
    if photo_path:
        # the client's own photo is the "before" for this kitchen; Alex adds the "after" when the job is done
        from .media import record
        record(who, "before", photo_path, "photo the client sent")
    # while the email is read: a stranger is looked up on the web (Tavily), a photo is looked at (Nemotron VL)
    from concurrent.futures import ThreadPoolExecutor
    from . import research, vision
    is_new = addr not in {p["email"] for p in PEOPLE}
    with ThreadPoolExecutor(max_workers=3) as ex:
        looked = ex.submit(research.look_up, who, addr, body) if is_new and not research.known(addr) else None
        seen = ex.submit(vision.describe, photo_path, body) if photo_path else None
        one = _triage_one(m)
        found = looked.result() if looked else research.known(addr)
        photo = seen.result() if seen else None
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
    plan = None
    label = one["cls"] or {}
    # a person typed this to Alex: even a message the sorter calls noise gets a short, honest answer
    # (intake marks it off-topic and the reply steers back to Alex's work); bulk mail never comes this way
    if label and not (growth_out or {}).get("asks"):
        # a delighted client already gets the thank-you (with the review link) from growth
        from .intake import assess
        from .scope import contract_for
        plan = assess(m, photo, has_contract=bool(contract_for(addr)), web=found, kind=label.get("kind") or "lead")
        from .reply import draft_reply
        reply_out = draft_reply(m, label, one["scope"], web=found, photo=photo, plan=plan, memory=memory)

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
        "research": found,
        "photo": {"path": m.get("photo"), "seen": photo} if photo_path else None,
        "plan": plan,
        "reply": {k: v for k, v in (reply_out or {}).items() if k != "held"} if reply_out else None,
        "held_back": [{"job": h["job"], "subject": h["subject"], "problems": h["problems"]} for h in held],
        "waiting_already": [s.get("waiting") for s in skipped],
        "calls": [{"tier": c["tier"], "purpose": c["purpose"], "ms": c["ms"]} for c in calls],
        "usd": round(sum(c["usd"] for c in calls), 4),
        "seconds": round(time.time() - t0, 1),
        "thread": thread(addr),
        "memory": memory,
        "lookalike": lookalike,
    }
