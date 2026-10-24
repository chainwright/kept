"""Cash guard: will there be enough money on the days it's needed?

Kept keeps the owner's invoices, bills and current balance (data/money.json) and
projects the next 30 days. The twist is honesty about other people's promises: an
invoice isn't expected on its due date but on the date *that client* usually pays,
learned from their past invoices. If the balance dips below zero, Kept says when, by
how much, and which unpaid invoice would fix it.

Overdue invoices get reminders on a ladder (friendly, firm, final). Code picks the
step from the days overdue; Nemotron Super writes the words; code checks the amount
and invoice number are right and that early steps don't threaten anyone. Every
reminder waits for the owner's Yes.
"""
from __future__ import annotations

import re
import statistics
from datetime import date, datetime, timedelta

from . import approvals
from .agent import _abstain, _msgs, read_notes_owner
from .llm import router
from .store import journal, now_iso, read_json, write_json
from .tools import notify
from .validators import Verdict, honest_email, sendable_text, shape

FILE = "money.json"
LADDER = [(1, "friendly", "a light, friendly reminder; assume they simply forgot"),
          (8, "firm", "a clear, polite reminder that gives a specific date to pay by, a week from today"),
          (22, "final", "a calm final notice: say that work on new requests pauses until it's settled")]
THREAT_WORDS = r"\b(legal|lawyer|court|collections?|late fee|penalt\w*|sue|lawsuit|pause|paused|stop work)\b"


def _d(s: str | None) -> date | None:
    return datetime.fromisoformat(s[:10]).date() if s else None


def load() -> dict:
    return read_json(FILE, {"balance": 0.0, "as_of": None, "invoices": [], "bills": []})


def payment_habit(client: str, book: dict | None = None) -> dict:
    """How late this client usually pays, from invoices they've already paid."""
    book = book or load()
    lates = [(_d(i["paid_on"]) - _d(i["due"])).days for i in book["invoices"]
             if i["client"] == client and i.get("paid_on")]
    if not lates:
        return {"paid": 0, "typical_days_late": 0}
    return {"paid": len(lates), "typical_days_late": max(0, int(statistics.median(lates)))}


def expected_payment(inv: dict, today: date, book: dict) -> date:
    habit = payment_habit(inv["client"], book)
    expected = _d(inv["due"]) + timedelta(days=habit["typical_days_late"])
    return max(expected, today + timedelta(days=1))  # nothing unpaid arrives in the past


def _bill_dates(bill: dict, start: date, end: date) -> list[date]:
    d = _d(bill["due"])
    out = []
    while d <= end:
        if d >= start and not bill.get("paid"):
            out.append(d)
        if bill.get("recurring") != "monthly":
            break
        m = d.month % 12 + 1
        d = d.replace(year=d.year + (d.month == 12), month=m)
    return out


def forecast(days: int = 30, today: date | None = None) -> dict:
    today = today or date.today()
    book = load()
    end = today + timedelta(days=days)
    events = []
    for inv in book["invoices"]:
        if inv.get("paid_on"):
            continue
        when = expected_payment(inv, today, book)
        if when <= end:
            events.append({"date": when, "amount": inv["amount"], "what": f"{inv['client']} pays #{inv['number']}",
                           "kind": "in", "invoice": inv["number"], "due": inv["due"]})
    for b in book["bills"]:
        for when in _bill_dates(b, today, end):
            events.append({"date": when, "amount": -b["amount"], "what": b["payee"], "kind": "out"})
    events.sort(key=lambda e: (e["date"], e["amount"]))  # same day: money out first, to be safe
    bal, low, timeline, short = book["balance"], (book["balance"], today), [], None
    for e in events:
        bal += e["amount"]
        timeline.append({**e, "date": e["date"].isoformat(), "balance": round(bal, 2)})
        if bal < low[0]:
            low = (bal, e["date"])
        if bal < 0 and short is None:
            short = {"date": e["date"].isoformat(), "gap": round(-bal, 2), "because": e["what"]}
    result = {"start": book["balance"], "timeline": timeline, "lowest": {"balance": round(low[0], 2),
              "date": low[1].isoformat()}, "short": short}
    if short:
        # which unpaid invoices, if they arrived on their due date instead, would close the gap?
        fixers = [e for e in events if e["kind"] == "in" and e["date"] > _d(short["date"])
                  and _d(e["due"]) <= _d(short["date"]) + timedelta(days=0)]
        result["fix"] = [{"invoice": f["invoice"], "what": f["what"], "amount": f["amount"],
                          "expected": f["date"].isoformat(), "due": f["due"]} for f in fixers]
    return result


def step_for(days_overdue: int) -> tuple[str, str] | None:
    step = None
    for start, name, tone in LADDER:
        if days_overdue >= start:
            step = (name, tone)
    return step


def chase(today: date | None = None) -> list[dict]:
    """Draft one reminder per overdue invoice that has no reminder waiting."""
    today = today or date.today()
    book = load()
    waiting = {a["args"].get("invoice") for a in approvals.pending() if a["kind"] == "send_email"}
    asked = []
    for inv in book["invoices"]:
        if inv.get("paid_on") or str(inv["number"]) in waiting:
            continue
        late = (today - _d(inv["due"])).days
        step = step_for(late)
        if not step:
            continue
        name, tone = step
        sent_steps = {r["step"] for r in inv.get("reminders", [])}
        if name in sent_steps:
            continue
        first = inv["client"].split(" ")[0]
        r = router.ask("draft", _msgs(
            f"Write {tone}. FROM {read_notes_owner()} TO {inv['client']} about invoice #{inv['number']} for "
            f"${inv['amount']:,.0f}, due {_d(inv['due']):%B %-d}, now {late} days overdue. Greet {first} by "
            f"first name, sign as {read_notes_owner()}. Mention the invoice number and amount once. "
            'Reply JSON: {"subject": "...", "body": "..."}', "follow_up"),
            purpose=f"chase #{inv['number']} ({name})", json_mode=True, max_tokens=500)
        try:
            d = r.json()
        except Exception as e:
            _abstain("chase", f"#{inv['number']}", Verdict(False, [f"model reply unusable: {e}"]))
            continue
        v = shape(d, {"subject": str, "body": str})
        if v:
            body = d["body"]
            v.merge(sendable_text(body))
            v.merge(honest_email(body, recipient_first=first, owner_first=read_notes_owner().split(" ")[0], today=today,
                                 allowed_dates={_d(inv["due"])}))
            if str(inv["number"]) not in body:
                v.add(f"the reminder doesn't mention invoice #{inv['number']}")
            amounts = {float(x.replace(",", "")) for x in re.findall(r"\$([\d,]+(?:\.\d\d)?)", body)}
            if float(inv["amount"]) not in amounts:
                v.add(f"the reminder doesn't state the amount ${inv['amount']:,.0f}")
            if amounts - {float(inv["amount"])}:
                v.add(f"the reminder mentions other amounts: {sorted(amounts - {float(inv['amount'])})}")
            if name != "final" and re.search(THREAT_WORDS, body, re.I):
                v.add(f"a {name} reminder shouldn't threaten anything ('{re.search(THREAT_WORDS, body, re.I).group(0)}')")
        if not v:
            _abstain("chase", f"#{inv['number']} {name}", v, d)
            continue
        habit = payment_habit(inv["client"], book)
        req = approvals.propose(
            "send_email", {"to": inv["contact"], "subject": d["subject"], "body": d["body"],
                           "invoice": str(inv["number"]), "step": name},
            summary=f"{name.capitalize()} reminder to {inv['client']}: #{inv['number']}, ${inv['amount']:,.0f}",
            why=(f"{late} days overdue, so the {name} step." +
                 (f" {first} usually pays {habit['typical_days_late']} days late." if habit["paid"] else "")),
            checks=["invoice number and amount match your records", "no other amounts",
                    "no threats" if name != "final" else "final step: pause on new work is allowed",
                    f"greets {first}"])
        if not req:
            continue
        notify.ask(req)
        asked.append(req)
    journal(f"Cash guard: drafted {len(asked)} payment reminder(s)")
    return asked


def mark_reminded(invoice: str, step: str) -> None:
    book = load()
    for inv in book["invoices"]:
        if str(inv["number"]) == str(invoice):
            inv.setdefault("reminders", []).append({"step": step, "ts": now_iso()})
    write_json(FILE, book)
