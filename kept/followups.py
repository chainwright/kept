"""A lead who got an estimate and went quiet: one gentle "how is your thinking going?" a week later.

Most people who ask for a kitchen price don't say no; they just stop answering while they think, and a
contractor who's up a ladder forgets them. Plain rules decide who: Kept worked out an estimate for them,
Alex's last message was the last word, a week has passed, no visit is booked, nothing else to them is
waiting, and they haven't been nudged already. One nudge, never two. Super writes it; code checks the
name, that every amount is the estimate they already have, and that it offers an easy way out.
Like everything else it waits for Alex's Yes.
"""
from __future__ import annotations

import re
from datetime import date, datetime

from . import approvals, estimate, schedule
from .agent import _abstain, _msgs, business, read_notes_owner
from .llm import router
from .store import journal, locked, now_iso, read_json, write_json
from .tools import notify
from .validators import Verdict, dollar_amounts, honest_email, sendable_text, shape

FILE = "followups.json"
AFTER_DAYS = 7
MAX_PER_DAY = 3


def candidates(today: date | None = None) -> tuple[list[dict], list[dict]]:
    from .reply import thread
    today = today or date.today()
    nudged = read_json(FILE, {})
    waiting = {a["args"].get("to", "").lower() for a in approvals.pending() if a["kind"] == "send_email"}
    visits = {e.get("contact") for e in schedule.load()["events"] if e.get("kind") == "visit"}
    ok, skipped = [], []
    for addr, est in read_json(estimate.FILE, {}).items():
        t = [x for x in thread(addr) if x["dir"] in ("in", "out")]
        if not t:
            continue
        name = next((x for x in t if x["dir"] == "in"), {}).get("name") or addr
        last = t[-1]
        days = (today - datetime.fromisoformat(last["ts"][:10]).date()).days
        why_not = ("they wrote last: it's Alex's turn, not a nudge" if last["dir"] == "in" else
                   "a visit is already booked" if addr in visits else
                   "something to them is already waiting for Yes" if addr in waiting else
                   "nudged once already" if addr in nudged else
                   f"only {days} day(s) since Alex's last message" if days < AFTER_DAYS else None)
        info = {"contact": addr, "days": days, "estimate": est, "topic": next((x["subject"] for x in t if x["dir"] == "in"), "")}
        (skipped if why_not else ok).append({**info, "why_not": why_not} if why_not else info)
    return ok, skipped


def propose(today: date | None = None) -> dict:
    from .agent import sender
    from .tools import mail
    today = today or date.today()
    ok, skipped = candidates(today)
    owner = read_notes_owner()
    drafted = []
    for c in ok[:MAX_PER_DAY]:
        first_mail = next((m for m in mail.inbox(500) if sender(m)[1] == c["contact"]), None)
        name = sender(first_mail)[0] if first_mail else c["contact"]
        first = name.split(" ")[0]
        est = c["estimate"]
        low, high = int(est.get("low") or 0), int(est.get("high") or 0)
        slots = schedule.free_slots(2)
        ask = ("You draft emails for " + owner + f", who runs {business()}. {name} asked about '{c['topic']}' and got a preliminary "
               f"estimate of ${low:,} to ${high:,} ({est.get('job', 'kitchen work').replace('_', ' ')}); {c['days']} days have passed "
               "with no answer. Write a short, warm check-in (3 or 4 sentences, under 90 words): ask how their thinking is going, "
               "offer to answer any question or to measure for free, and name these visit times exactly as written: "
               + "; ".join(s["label"] for s in slots) + ". Give them an easy way out (if the timing isn't right, no problem). "
               f"No pressure, no discounts, no new prices. Greet {first}, sign as {owner.split(' ')[0]}. Plain text. "
               'Reply JSON: {"subject": "...", "body": "..."}')
        from .reply import _names_a_slot
        problems, v, e, body = [], Verdict(False, ["not tried"]), {}, ""
        for attempt in (1, 2):
            r = router.ask("draft", _msgs(ask + ("\n\nYOUR LAST DRAFT FAILED: " + "; ".join(problems) if problems else "")),
                           purpose=f"check in with {c['contact']}" + (" (second try)" if attempt > 1 else ""),
                           json_mode=True, max_tokens=400)
            try:
                e = r.json()
            except Exception as ex:
                v = Verdict(False, [f"model reply unusable: {ex}"])
                break
            v = shape(e, {"subject": str, "body": str})
            if v:
                body = e["body"].strip()
                v.merge(sendable_text(body, max_chars=800))
                v.merge(honest_email(body, recipient_first=first, owner_first=owner.split(" ")[0]))
                extra = dollar_amounts(body) - {low, high}
                if extra:
                    v.add(f"the check-in names amounts that aren't their estimate: {sorted(extra)}")
                if not re.search(r"no (problem|worries|pressure)|if (the )?timing|whenever you|not the right time|no rush", body, re.I):
                    v.add("the check-in doesn't give them an easy way out")
                if slots and not _names_a_slot(body, slots):
                    v.add("the check-in offers a visit but names none of the times from Alex's calendar")
            if v:
                break
            problems = v.problems
        if not v:
            _abstain("followup", c["contact"], v, e)
            continue
        req = approvals.propose("send_email", {"to": c["contact"], "subject": e["subject"], "body": body},
                                summary=f"Check in with {name}: the estimate went quiet ({c['days']} days)",
                                why=f"Kept gave {first} a preliminary ${low:,}–${high:,} estimate and heard nothing since",
                                checks=[f"greets {first}", "only the estimate they already have", "an easy way out"],
                                reasoning=r.reasoning, model_label="Nemotron Super")
        if req:
            notify.ask(req)
            with locked():
                rows = read_json(FILE, {})
                rows[c["contact"]] = now_iso()
                write_json(FILE, rows)
            drafted.append(req["id"])
    journal(f"Quiet leads: {len(drafted)} gentle check-ins drafted, {len(skipped)} left alone")
    return {"drafted": drafted, "skipped": skipped}
