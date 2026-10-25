"""Answering someone who just wrote: a draft reply that only says what Alex can stand behind.

Super writes the reply from facts code gathers (the thread so far, Alex's rates and hours, what
the signed agreement says, open promises both ways, unpaid invoices). Code then checks it:
the right name, no prices that didn't come from Alex's records, no dates that have passed, and
every promised date is run through "Before you send", so a reply never commits Alex to a day
history says Alex won't hit. The draft waits for Yes like everything else.
"""
from __future__ import annotations

import re
from datetime import date

from . import approvals, ledger, money, precheck
from .agent import _abstain, _msgs, business, read_notes_owner, sender
from .llm import router
from .store import journal, locked, now_iso, read_json, read_notes
from .tools import mail, notify
from .validators import Verdict, dollar_amounts, honest_email, language_of, sendable_text, shape, times_not_offered


def _rate() -> int | None:
    m = re.search(r"hourly rate:\s*\$?\s*(\d+)", read_notes(), re.I)
    return int(m.group(1)) if m else None


def _names_a_slot(body: str, slots: list[dict]) -> bool:
    """An offered time is named if its weekday is there (English), or its day of the month and its
    hour are (any language: "26 октября в 17:30")."""
    from datetime import date as _date
    body = re.sub(r"\b(\d{1,2})\s?h\s?(\d{2})\b", r"\1:\2", body)   # French "17 h 30" is 17:30
    low = body.lower()
    for s in slots:
        d = _date.fromisoformat(s["date"])
        hh, mm = (int(x) for x in s["time"].split(":"))
        h12 = hh - 12 if hh > 12 else hh
        if f"{d:%A}".lower() in low:
            return True
        if re.search(rf"\b{d.day}\b", body) and (s["time"] in body or f"{h12}:{mm:02d}" in body):
            return True
    return False


_DAY = (r"(monday|tuesday|wednesday|thursday|friday|saturday|sunday|tomorrow|the end of|end of|"
        r"(jan|feb|mar|apr|may|jun|jul|aug|sep|oct|nov|dec)\w*\.? \d{1,2})")
QUOTE_BY_DAY = re.compile(rf"\b(quote|estimate|price)\b[^.\n]{{0,60}}\b(by|before)\s+{_DAY}|\b(by|before)\s+{_DAY}[^.\n]{{0,60}}\b(quote|estimate)\b"
                          rf"|\b(quote|estimate)\b[^.\n]{{0,25}}\bon\s+{_DAY}", re.I)


def thread(addr: str) -> list[dict]:
    """Every message between Alex and this address: theirs, Alex's sent replies, drafts waiting."""
    addr = addr.lower()
    out = []
    for m in mail.inbox(500):
        if sender(m)[1] == addr:
            out.append({"dir": "in", "id": m["id"], "subject": m["subject"], "body": m["body"],
                        "ts": m.get("ts") or f"{m['date']}T08:00:00+00:00"})
    for a in approvals.recent(10000):
        if a["kind"] == "send_email" and a["args"].get("to", "").lower() == addr:
            state = {"pending": "draft", "done": "out", "approved": "out"}.get(a["status"], a["status"])
            out.append({"dir": state, "id": a["id"], "subject": a["args"].get("subject", ""),
                        "body": a["args"].get("body", ""), "ts": a.get("finished") or a["created"]})
    return sorted(out, key=lambda x: x["ts"])


def facts_about(addr: str, name: str, exclude_source: str = "") -> dict:
    """exclude_source: leave out promises read from the email being answered; otherwise the reply
    treats the client's own request as something Alex already agreed to."""
    addr = addr.lower()
    book = money.load()
    invs = [i for i in book["invoices"] if i["contact"].lower() == addr]
    today = date.today().isoformat()
    from .scope import contract_for
    return {
        "unpaid_invoices": [{"number": i["number"], "amount": i["amount"], "due": i["due"],
                             "overdue": i["due"] < today} for i in invs if not i.get("paid_on")],
        "pays_late_by_days": money.payment_habit(invs[-1]["client"], book).get("typical_days_late") if invs else None,
        "has_signed_agreement": bool(contract_for(addr)),
        "alex_owes_them": [r["text"] for r in ledger.open_sorted(which="i_owe")
                           if (r.get("contact") or "").lower() == addr and r.get("source") != exclude_source],
        "they_owe_alex": [r["text"] for r in ledger.open_sorted(which="owed_to_me")
                          if (r.get("contact") or "").lower() == addr and r.get("source") != exclude_source],
    }


def supersede(addr: str, newer: str) -> list[str]:
    """A newer email from the same person makes an unsent draft to them stale. Mark it replaced
    (never deleted) so the one-message-per-person rule leaves room for the up-to-date reply."""
    replaced = []
    with locked():
        rows = read_json(approvals.FILE, [])
        for a in rows:
            if a["status"] == "pending" and a["kind"] == "send_email" and a["args"].get("to", "").lower() == addr.lower():
                a["status"], a["decided"], a["by"] = "replaced", now_iso(), "kept"
                a["note"] = f"they wrote again ({newer}); a fresh reply replaces this draft"
                replaced.append(a["id"])
        if replaced:
            from .store import write_json
            write_json(approvals.FILE, rows)
    return replaced


def draft_reply(m: dict, label: dict, scope_res: dict | None, web: dict | None = None,
                photo: dict | None = None, plan: dict | None = None, supersede_old: bool = True,
                memory: dict | None = None) -> dict:
    """Returns {"approval": ..., "held": ..., "dates": [...], "replaced": [...]}"""
    name, addr = sender(m)
    first = name.split(" ")[0]
    owner = read_notes_owner()
    rate = _rate()
    facts = facts_about(addr, name, exclude_source=m["id"])
    scope_lines = []
    allowed = {rate} if rate else set()
    if rate:
        mh = re.search(r"(\d+)-hour minimum", read_notes(), re.I)
        allowed.add(rate * int(mh.group(1)) if mh else rate * 2)   # the minimum charge, from Alex's own notes
    for r in (scope_res or {}).get("requests", []):
        meaning = {"in_scope": "covered by the agreement, no extra charge, never quote a price for it",
                   "out_of_scope": "not in the agreement", "unclear": "the agreement doesn't settle it; Alex will check",
                   "already_promised": "Alex already promised this"}.get(r["verdict"], r["verdict"])
        line = f"- '{r['request']}': {meaning}"
        if r.get("price"):
            line += f", price ${int(r['price'])} (computed from the hourly rate)"
            allowed.add(int(r["price"]))
        scope_lines.append(line)
    priced = [int(r["price"]) for r in (scope_res or {}).get("requests", []) if r.get("price")]
    if len(priced) > 1:
        allowed.add(sum(priced))
    allowed |= {int(i["amount"]) for i in facts["unpaid_invoices"]}
    # published prices in Alex's notes ("from $2,400", "$120 a month") are Alex's own words too
    allowed |= {int(x.replace(",", "")) for x in re.findall(r"\$([\d,]+)", read_notes().split("## Offers")[0])}
    from .intake import reply_rules
    rules_text, plan_amounts, must = reply_rules(plan or {})
    allowed |= plan_amounts
    allowed |= dollar_amounts(m["body"])   # their own numbers ("I'll only pay $500") may be repeated back to them
    if memory and memory.get("estimate"):
        allowed |= {memory["estimate"]["low"], memory["estimate"]["high"]}   # the estimate Kept already gave them
    convo = "\n\n".join(f"{'THEM' if t['dir'] == 'in' else owner.upper()} ({t['ts'][:10]}): {t['body'][:800]}"
                        for t in thread(addr)[-6:] if t["dir"] in ("in", "out") and t["id"] != m["id"])
    today = date.today()
    prompt = (f"Today is {today.isoformat()} ({today:%A}). You draft replies for {owner}, who runs {business()}. Write {owner}'s reply to {name} <{addr}>. Use ONLY these facts; if they ask something the facts "
        "don't answer, say Alex will check and come back, or ask them a short question. Never invent a total "
        "price for a new project: use only the prices in Alex's services, and offer the free intro call or a "
        "written quote. If extra work "
        "is outside the agreement, say so kindly, give the price listed below and ASK whether they want it; never say "
        "Alex will do extra work before they've said yes to its price. Don't agree to a deadline "
        "for new work that hasn't been scoped or priced yet: offer the call, a visit or the "
        "quote first. Small things (sending a quote, a file, a call) may get a day; name it plainly ('by "
        "Tuesday'). Never name visit times or dates for a visit except ones given below. Don't promise to send a "
        "written quote by a set day before the visit. Write in the language of their email. Greet them by first name exactly as their email writes it ("
        f"{first}), sign as Alex, under 140 words, plain text (no markdown). "
        'Reply JSON: {"subject": "...", "body": "..."}\n\n'
        f"ABOUT ALEX:\n{read_notes().split('## Offers')[0].strip()}\n\n"
        f"WHAT KEPT KNOWS ABOUT {name.upper()}: {facts}\n"
        + (f"\nSCOPE CHECK ON THIS EMAIL:\n" + "\n".join(scope_lines) + "\n" if scope_lines else "")
        + (f"\nEARLIER MESSAGES:\n{convo}\n" if convo else "")
        + (f"\nTHEY'VE WRITTEN BEFORE: first on {memory['since']} about '{memory['topic']}', last {memory['days']} day(s) ago"
           + (f"; Kept's preliminary estimate then: ${memory['estimate']['low']:,} to ${memory['estimate']['high']:,}" if memory.get('estimate') else "")
           + (f"; a visit is booked for {memory['visit']}" if memory.get('visit') else "")
           + ". Open by picking up where you left off, in one short natural sentence (for example, how their "
             "thinking on it is going), then answer their new email.\n" if memory and memory.get("days", 0) >= 2 else "")
        + ("\nWHAT THE WEB SAYS ABOUT THEM (checked against the pages; mention at most one, only if it helps):\n"
           + "\n".join(f"- {f['text']}" for f in web["facts"]) + "\n" if web and web.get("facts") else "")
        + (f"\nTHEIR PHOTO, AS NEMOTRON VL SAW IT: {photo}\n" if photo else "")
        + (f"\nHOW ALEX HANDLES THIS KIND OF JOB (follow it): {rules_text}\n" if rules_text else "")
        + f"\nTHEIR NEW EMAIL (subject: {m['subject']}):\n{m['body']}")
    tries, problems = 0, []
    while True:
        tries += 1
        ask = prompt if not problems else (prompt + "\n\nYOUR LAST DRAFT FAILED ALEX'S CHECKS. Write it again and fix "
                                           "exactly these: " + "; ".join(problems))
        r = router.ask("draft", _msgs(ask, "follow_up"), purpose=f"reply to {m['id']}" + (" (second try)" if tries > 1 else ""),
                       json_mode=True, max_tokens=700)
        try:
            e = r.json()
        except Exception as ex:
            return {"held": _abstain("reply", m["subject"], Verdict(False, [f"model reply unusable: {ex}"]))}
        v = shape(e, {"subject": str, "body": str})
        dates = []
        if v:
            body = e["body"].replace("**", "").strip()  # an email is plain text
            if body and not re.search(rf"\b{re.escape(owner.split(' ')[0])}\b", body[-60:]):
                body += f"\n\n{owner.split(' ')[0]}"   # a short note still ends with Alex's name
            v.merge(sendable_text(body, max_chars=1200))
            v.merge(honest_email(body, recipient_first=first, owner_first=owner.split(" ")[0]))
            amounts = dollar_amounts(body)
            if amounts - allowed:
                v.add(f"the reply names amounts that aren't in Alex's records: {sorted(amounts - allowed)}")
            # a quote Alex already owes them (Maria's revised quote) has its own date, checked by Before you send
            owes_a_quote = any(re.search(r"\b(quote|estimate)\b", t, re.I) for t in facts["alex_owes_them"])
            if not (plan or {}).get("booked_label") and not (plan or {}).get("on_site") and not owes_a_quote \
                    and QUOTE_BY_DAY.search(body):
                v.add("the reply promises a written quote by a set day before the measuring visit; offer the visit first")
            wrong = times_not_offered(body, (plan or {}).get("slots") or []) if (plan or {}).get("slots") else []
            if wrong:
                v.add(f"the reply names visit times Alex's calendar didn't offer: {', '.join(wrong)}")
            theirs = language_of(m["body"])
            if theirs != "en" and language_of(body) != theirs:
                v.add(f"the reply isn't in the language they wrote in ({theirs})")
            for need in must:
                if need == "SLOTS":
                    if not _names_a_slot(body, (plan or {}).get("slots") or []):
                        v.add("the reply doesn't offer any of the visit times from Alex's calendar")
                    continue
                options = need.split("|")
                if not any(o.lower() in body.lower() for o in options):
                    v.add(f"the reply leaves out what the next step needs: {' or '.join(options)}")
            if v:
                # every date Alex commits to goes through Before you send
                from .validators import dates_in
                given = {d.isoformat() for t in thread(addr) if t["dir"] == "out" for d in dates_in(t["body"], today)}
                pc = precheck.check(body, name, already_promised=given)
                for p in pc.get("promises", []):
                    if p.get("advice"):
                        dates.append({"promise": p["text"], "said": p["when_words"], "usual": p["advice"]["why"],
                                      "moved_to": p["advice"]["suggested"]})
                if dates:
                    rw = pc.get("rewrite") or {}
                    if rw.get("ok") and rw.get("text"):
                        body = rw["text"]
                    else:
                        v.add("the reply promises a date Alex usually misses, and the safer wording couldn't be checked")
            e["body"] = body
        if v or tries >= 3:
            break
        # one second try with the checks' own words; the first failure stays in the record
        _abstain("reply", m["subject"] + " (first draft)", v, e)
        problems = v.problems
    if not v:
        return {"held": _abstain("reply", m["subject"], v, e)}
    replaced = supersede(addr, m["id"]) if supersede_old else []
    subject = e["subject"] if e["subject"].lower().startswith("re:") else f"Re: {m['subject']}"
    checks = [f"greets {first}, signed by {owner.split(' ')[0]}", "every price comes from Alex's records",
              "no dates that have passed"]
    if dates:
        checks.append("dates moved to when Alex usually delivers: " +
                      ", ".join(f"{d['said']} -> {date.fromisoformat(d['moved_to']):%a %b %-d}" for d in dates))
    req = approvals.propose(
        "send_email", {"to": addr, "subject": subject, "body": e["body"], "in_reply_to": m["id"]},
        summary=f"Reply to {name}: {subject}",
        why=f"{name} wrote: {label.get('one_line', m['subject'])}" if label else f"{name} wrote to you",
        checks=checks, reasoning=r.reasoning, model_label="Nemotron Super")
    if req:
        notify.ask(req)
    return {"approval": req, "dates": dates, "replaced": replaced}


ANSWER_WITHIN_DAYS = 3


def answer_new(mail_ids: list[str] | None = None) -> dict:
    """Draft a reply to every recent email from a client or a lead that asks for one, unless something
    is already waiting for that person (a reminder, an offer, a review request: those come first).
    Runs after the morning's other jobs, and after the hourly sort."""
    from .intake import assess
    from .parallel import pmap
    from .research import known
    from .scope import contract_for

    labels = read_json("labels.json", {})
    scopes = {s["mail"]: s for s in read_json("scope.json", [])}
    waiting = {a["args"].get("to", "").lower() for a in approvals.pending() if a["kind"] == "send_email"}
    today = date.today()
    todo = []
    for m in mail.inbox(200):
        lab = labels.get(m["id"]) or {}
        if mail_ids is not None and m["id"] not in mail_ids:
            continue
        if lab.get("kind") not in ("lead", "client") or not lab.get("needs_reply"):
            continue
        try:
            if (today - date.fromisoformat(str(m.get("date"))[:10])).days > ANSWER_WITHIN_DAYS:
                continue
        except ValueError:
            continue
        addr = sender(m)[1]
        if addr in waiting or any(t["dir"] == "out" and t["ts"] > (m.get("ts") or m["date"]) for t in thread(addr)):
            continue
        waiting.add(addr)
        todo.append((m, lab))

    def one(item):
        m, lab = item
        addr = sender(m)[1]
        plan = assess(m, None, has_contract=bool(contract_for(addr)), web=known(addr))
        return draft_reply(m, lab, scopes.get(m["id"]), web=known(addr), plan=plan, supersede_old=False)

    done = pmap(one, todo)
    drafted = [d["approval"]["id"] for d in done if d.get("approval")]
    journal(f"Answered new mail: {len(drafted)} replies drafted, {len(todo) - len(drafted)} held back")
    return {"considered": len(todo), "drafted": drafted}

