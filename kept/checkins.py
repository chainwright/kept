"""Staying in touch: a short check-in with past clients, at the right time and never pushy.

A client who had one small job done (a hinge, a drawer) is the easiest next job, if they remember
you. (Clients with bigger past projects are covered by seasonal offers instead.) A month or two later Kept drafts a two-line note: how is the work holding up,
does anything else need attention, and, only when Alex's records give a reason (an estimate they
didn't go ahead with, a photo that showed tired fronts), one idea with its "from" price.

Plain rules decide who: the work is finished and paid, at least CHECKIN_AFTER_DAYS ago; nothing
open either way; no overdue invoice; no message to them in the last 60 days. At most two a day.
"""
from __future__ import annotations

import re
from datetime import date, datetime

from . import approvals, ledger, money
from .agent import _abstain, _msgs, business, read_notes_owner
from .llm import router
from .store import journal, locked, now_iso, read_json, read_notes, write_json
from .tools import notify
from .validators import Verdict, honest_email, sendable_text, shape

FILE = "checkins.json"
CHECKIN_AFTER_DAYS = 30
EVERY_DAYS = 60
MAX_PER_DAY = 2


def _min_project() -> int:
    m = re.search(r"minimum (?:project )?price[^\d]*\$?\s*([\d,]+)", read_notes(), re.I)
    return int(m.group(1).replace(",", "")) if m else 900


def candidates(today: date | None = None) -> tuple[list[dict], list[dict]]:
    today = today or date.today()
    book = money.load()
    sent = read_json(FILE, [])
    recent_mail = {a["args"].get("to", "").lower(): a for a in approvals.recent(500)
                   if a["kind"] == "send_email" and (today - datetime.fromisoformat(a["created"][:10]).date()).days < EVERY_DAYS}
    by_client: dict[str, list[dict]] = {}
    for inv in book["invoices"]:
        by_client.setdefault(inv["client"], []).append(inv)
    ok, skipped = [], []
    for client, invs in by_client.items():
        contact = invs[-1]["contact"].lower()
        unpaid = [i for i in invs if not i.get("paid_on")]
        last_paid = max((datetime.fromisoformat(i["paid_on"]).date() for i in invs if i.get("paid_on")), default=None)
        open_rows = [r for r in ledger.items("open") if (r.get("contact") or "").lower() == contact]
        done = [r for r in ledger.items() if r["status"] == "done" and (r.get("contact") or "").lower() == contact]
        last_inv = max(invs, key=lambda i: i["issued"])
        why_not = ("has unpaid work" if unpaid else
                   "a bigger past job: seasonal offers cover them" if last_inv["amount"] >= _min_project() else
                   "something is still open between you" if open_rows else
                   "the last job was too recent" if not last_paid or (today - last_paid).days < CHECKIN_AFTER_DAYS else
                   "you wrote to them recently" if contact in recent_mail else
                   f"checked in within {EVERY_DAYS} days" if any(s["client"] == client and
                       (today - datetime.fromisoformat(s["ts"][:10]).date()).days < EVERY_DAYS for s in sent) else None)
        info = {"client": client, "contact": contact, "days_since": (today - last_paid).days if last_paid else None,
                "work_done": [r["text"] for r in done][-4:]}
        (skipped if why_not else ok).append({**info, "why_not": why_not} if why_not else info)
    return ok, skipped


def propose(today: date | None = None) -> dict:
    today = today or date.today()
    ok, skipped = candidates(today)
    out = {"ts": now_iso(), "asked": [], "skipped": skipped}
    prices = set(int(x.replace(",", "")) for x in re.findall(r"\$([\d,]+)", read_notes().split("## Offers")[0]))
    services = read_notes().split("## Services")[-1].split("## ")[0].strip()
    for c in ok[:MAX_PER_DAY]:
        first = c["client"].split(" ")[0]
        r = router.ask("draft", _msgs(
            f"{read_notes_owner()} runs {business()}. Write a short, warm check-in email FROM {read_notes_owner()} TO "
            f"{c['client']}, whose last job finished {c['days_since']} days ago. What Alex did for them: "
            f"{c['work_done']}. Ask how it's holding up and whether anything else needs attention. If what Alex did "
            "for them shows an estimate they didn't go ahead with, or an obvious next step, mention ONE idea in a "
            "sentence with its 'from' price from the list below, otherwise none. No discount, no pressure, no "
            f"'limited time'. Greet {first}, sign as {read_notes_owner()}. Under 90 words. "
            'Reply JSON: {"subject": "...", "body": "..."}\n\nAlex\'s services:\n' + services, "follow_up"),
            purpose=f"check-in {c['client']}", json_mode=True, max_tokens=400)
        try:
            e = r.json()
        except Exception as ex:
            _abstain("check-in", c["client"], Verdict(False, [f"model reply unusable: {ex}"]))
            continue
        v = shape(e, {"subject": str, "body": str})
        if v:
            body = e["body"]
            v.merge(sendable_text(body, max_chars=800))
            v.merge(honest_email(body, recipient_first=first, owner_first=read_notes_owner().split(" ")[0]))
            amounts = {int(x.replace(",", "")) for x in re.findall(r"\$([\d,]+)", body)}
            if amounts - prices:
                v.add(f"names prices that aren't on Alex's list: {sorted(amounts - prices)}")
            if re.search(r"\b(limited time|act now|hurry|last chance|discount|% off)\b", body, re.I):
                v.add("pressure or a discount in a check-in")
        if not v:
            _abstain("check-in", c["client"], v, e)
            continue
        req = approvals.propose(
            "send_email", {"to": c["contact"], "subject": e["subject"], "body": e["body"]},
            summary=f"Check in with {c['client']} ({c['days_since']} days since the last job)",
            why="Past clients are the easiest next job if they remember you. Last work: " + "; ".join(c["work_done"][-2:]),
            checks=[f"finished and paid {c['days_since']} days ago", "nothing open either way",
                    f"no message to them in {EVERY_DAYS} days", "prices only from your list, no discount"])
        if req:
            with locked():
                rows = read_json(FILE, [])
                rows.append({"client": c["client"], "ts": now_iso(), "approval": req["id"]})
                write_json(FILE, rows)
            notify.ask(req)
            out["asked"].append(req["id"])
    write_json("checkins_last.json", out)
    journal(f"Check-ins: {len(out['asked'])} drafted, {len(skipped)} not now")
    return out
