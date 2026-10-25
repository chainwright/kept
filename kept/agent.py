"""What Kept actually does. Each job follows the same loop:

    gather facts -> a Nemotron model proposes -> code verifies -> act, ask, or abstain

Local bookkeeping (adding to the ledger, writing the journal) happens on its own.
Anything that reaches another person goes through the approval gate.
"""
from __future__ import annotations

import json
import re
from datetime import date
from typing import Any

from . import approvals, ledger
from .config import ROOT
from .llm import BudgetExceeded, router
from .store import append_audit, journal, locked, now_iso, read_journal, read_json, read_notes, write_json
from .tools import mail, notify
from email.utils import parseaddr

from .validators import Verdict, grounded, honest_email, one_of, plausible_due, sendable_text, shape, source_id

SYSTEM = ("You are Kept, an operator for a one-person business. You are careful and plain-spoken. "
          "You never invent facts. When asked for JSON, reply with JSON only.")


SKILLS = ROOT / "skills"


def skill_path(name: str):
    """The owner's own copy of a skill (with the rules Kept learned for them) lives with their data;
    the shipped skill in skills/ is the starting point and is never written to."""
    from .store import data_dir
    mine = data_dir() / "skills" / f"{name}.md"
    return mine if mine.exists() else SKILLS / f"{name}.md"


def skill(name: str) -> str:
    """Skills are plain markdown the owner can edit; they travel with every prompt that uses them."""
    p = skill_path(name)
    return p.read_text().strip() if p.exists() else ""


def _msgs(user: str, skill_name: str | None = None) -> list[dict]:
    system = SYSTEM + ("\n\n" + skill(skill_name) if skill_name else "")
    return [{"role": "system", "content": system}, {"role": "user", "content": user}]


def _abstain(job: str, subject: str, verdict: Verdict, payload: Any = None) -> dict:
    rec = {"ts": now_iso(), "job": job, "subject": subject, "problems": verdict.problems,
           "payload": payload}
    with locked():
        rows = read_json("abstained.json", [])
        rows.append(rec)
        write_json("abstained.json", rows[-200:])
    append_audit("abstained", job=job, subject=subject, problems=verdict.problems)
    journal(f"Held back on {job} ({subject}): " + "; ".join(verdict.problems))
    return rec


def sender(m: dict) -> tuple[str, str]:
    """(display name, address) from the From header. Facts like these come from code, not the model:
    in a live run the model once named the owner as the person a promise was owed to."""
    name, addr = parseaddr(m.get("from", ""))
    return (name or addr.split("@")[0]).strip(), addr.strip().lower()


# --------------------------------------------------------------------------- inbox
def triage_inbox() -> dict:
    """Sort new mail (Nano) and pull out anything the owner promised (Super + checks).
    Each email is handled on its own, so they run side by side."""
    from .parallel import pmap

    seen = set(read_json("seen_mail.json", []))
    new = [m for m in mail.inbox(50) if m["id"] not in seen]
    report = {"new": len(new), "commitments": [], "abstained": 0, "labels": {}}
    for one in pmap(_triage_one, new):
        if one["cls"] is None:
            report["abstained"] += 1
            continue
        report["labels"][one["id"]] = one["cls"]
        if one["scope"] is not None:
            report.setdefault("scope", []).append(one["scope"])
        report["commitments"] += one["commitments"]
        seen.add(one["id"])
    write_json("seen_mail.json", sorted(seen))
    labels = read_json("labels.json", {})
    labels.update(report["labels"])
    write_json("labels.json", labels)
    journal(f"Triaged {report['new']} new emails, found {len(report['commitments'])} commitments")
    return report


def _triage_one(m: dict) -> dict:
    out = {"id": m["id"], "cls": None, "scope": None, "commitments": []}
    try:
        cls = router.ask("classify", _msgs(
            "Classify this email for a solo business owner. Reply JSON: "
            '{"kind": "lead|client|bill|personal|noise", "needs_reply": true|false, '
            '"one_line": "<=15 words"}\n\n'
            f"From: {m['from']}\nSubject: {m['subject']}\n\n{m['body'][:3000]}", "triage"),
            purpose=f"triage {m['id']}", json_mode=True, max_tokens=200).json()
    except BudgetExceeded:
        raise
    except Exception as e:
        _abstain("triage", m["subject"], Verdict(False, [f"model reply unusable: {e}"]))
        return out
    v = shape(cls, {"kind": str, "needs_reply": bool, "one_line": str})
    v.merge(one_of(cls.get("kind"), ["lead", "client", "bill", "personal", "noise"], "kind"))
    if not v:
        _abstain("triage", m["subject"], v, cls)
        return out
    out["cls"] = cls
    pending_decision = []
    if cls["kind"] == "client":
        from . import scope
        if scope.contract_for(sender(m)[1]):
            # scope first: extra work is a decision for the owner, not a promise they've made
            res = scope.review(m) or {}
            out["scope"] = {"mail": m["id"], **res}
            # only clear extra work waits for the owner's decision. An "unclear" request stays in
            # the ledger: losing a promise is worse than tracking one too many (a visitor's "send me
            # the menu PDF by Thursday" was judged unclear and vanished)
            pending_decision = [r["email_quote"] for r in res.get("requests", [])
                                if r["verdict"] == "out_of_scope"
                                and not _owner_already_said(r.get("email_quote", ""))]
    if cls["kind"] != "noise":
        out["commitments"] = _extract_commitments(m, cls["kind"], skip=pending_decision)
    return out


def _owner_already_said(quote: str) -> bool:
    """'you mentioned you'd fix the form' is a promise already made, whatever the contract says.
    Eval run: the scope check called it 'unclear', the promise was skipped, and a discount offer
    then went to the client still waiting for the fix."""
    return bool(re.search(r"\byou(?:'d|'ll| would| will| said| mentioned| promised| told me| agreed)\b", quote or "", re.I))


def _shared_words(a: str, b: str) -> int:
    w = lambda t: {x for x in re.findall(r"[a-z]{4,}", t.lower())} - {"could", "would", "page", "with", "your", "please"}
    return len(w(a) & w(b))


def _is_client(addr: str) -> bool:
    from . import money
    return any(i.get("contact", "").lower() == addr for i in money.load()["invoices"])


def _extract_commitments(m: dict, kind: str = "", skip: list[str] | None = None) -> list[dict]:
    """Promises in this thread, in both directions, each with the words that prove it."""
    out = []
    owner, (name, addr) = read_notes_owner(), sender(m)
    try:
        data = router.ask("extract", _msgs(
            f"This email was sent TO the business owner, {owner}, BY {name}. Find two kinds of promise:\n"
            f"- mine: things {owner} promised or must do for {name}. Write each as a short instruction to "
            f"{owner}, naming the person (e.g. 'Send Maria the revised quote').\n"
            f"- theirs: things {name} promised to do for {owner} (send files, pay an invoice, give feedback). "
            f"Write each as what {name} owes (e.g. 'Priya pays invoice #118').\n"
            "For each, copy the exact words from the email that show it. Reply JSON: "
            '{"mine": [{"text": "...", "due": "YYYY-MM-DD or null", "quote": "exact words"}], '
            '"theirs": [{"text": "...", "due": "YYYY-MM-DD or null", "quote": "exact words"}]}. '
            f"Today is {date.today().isoformat()} ({date.today():%A}). Empty lists are fine.\n\n"
            f"From: {m['from']}\nSubject: {m['subject']}\n\n{m['body'][:4000]}", "extract"),
            purpose=f"extract {m['id']}", json_mode=True, max_tokens=600).json()
    except Exception as e:
        _abstain("extract", m["subject"], Verdict(False, [f"model reply unusable: {e}"]))
        return out
    batches = [("i_owe", data.get("mine") or data.get("items") or []), ("owed_to_me", data.get("theirs") or [])]
    if kind == "bill" and not _is_client(addr):
        # a vendor's bill is always something the owner pays, whatever the model filed it under;
        # a client writing about paying the owner is the opposite, so clients are excluded
        batches = [("i_owe", batches[0][1] + batches[1][1])]
    for direction, items in batches:
        for it in items[:5]:
            v = shape(it, {"text": str, "quote": str})
            quoting = re.search(r"\b(quote|estimate|proposal|rates|pricing|price)\b", it["text"], re.I)
            if v and skip and direction == "i_owe" and not quoting and not _owner_already_said(it.get("quote", "")) and any(
                    _shared_words(it.get("quote", "") + " " + it["text"], q) >= 2 for q in skip):
                # "build the online ordering page" waits for a decision; "send the quote for it" is a promise
                journal(f"Not adding '{it['text']}' as a promise: it's extra work waiting for your decision")
                continue
            if v and len(it["text"].split()) < 3:
                v.add(f"'{it['text']}' is too short to be a promise anyone could act on")
            if v:
                v.merge(grounded([{"source": m["id"], "quote": it.get("quote", "")}],
                                 {m["id"]: m["subject"] + "\n" + m["body"]}))
                v.merge(plausible_due(it.get("due")))
            if not v:
                _abstain("extract", it.get("text", m["subject"]) if isinstance(it, dict) else m["subject"], v, it)
                continue
            text = it["text"].strip()
            if direction == "i_owe":
                # the model sometimes copies the client's own words ("Send me your rates"); in the
                # owner's ledger "me" is the client
                first = name.split(" ")[0]
                text = re.sub(r"\bme\b", first, text)
                text = re.sub(r"\bmy\b", f"{first}'s", text, flags=re.I)
            out.append(ledger.add(text[:1].upper() + text[1:], who=name, contact=addr, due=it.get("due"),
                                  source=m["id"], origin="inbox", direction=direction, quote=it["quote"]))
    return out


# --------------------------------------------------------------------------- follow-ups
def follow_ups(limit: int = 3) -> list[dict]:
    """Draft replies for overdue or due-today promises (Super), checked before asking."""
    mails = {m["id"]: m for m in mail.inbox(50)}
    asked = []
    today = date.today()
    for row in ledger.open_sorted(today):
        if len(asked) >= limit:
            break
        if any(a.get("ledger_id") == row["id"] for a in approvals.pending()):
            continue
        theirs = ledger.direction(row) == "owed_to_me"
        if theirs and re.search(r"invoice\s*#?\d+", row["text"], re.I):
            continue  # unpaid invoices get the cash guard's ladder, with amount and number
        overdue = ledger.days_overdue(row, today)
        due_soon = row.get("due") and row["due"][:10] <= today.isoformat()
        src = mails.get(row.get("source", ""))
        # our own promises: act when due; theirs: only nudge once they are actually late
        if not (src and (overdue if theirs else due_soon)):
            continue
        full, to = sender(src)
        name = full.split(" ")[0]
        if theirs:
            status = (f"{full} promised this to {read_notes_owner()} and it is {overdue} day(s) late. Write a "
                      "friendly two-line nudge asking when to expect it. No guilt, no threats, no new deadlines.")
        else:
            status = (f"It is {overdue} day(s) late; apologise in one sentence and say it will arrive today."
                      if overdue else "It is due today; say it will arrive today.")
        r = router.ask("draft", _msgs(
            f"Today is {today.isoformat()} ({today:%A}). Write a short, warm email FROM {read_notes_owner()} "
            f"TO {full} about this: '{row['text']}'. {status} Greet {name} by first name, sign as "
            f"{read_notes_owner()}. Answer any open question from their email only if the answer is "
            "obvious; otherwise say you'll confirm. Do not invent facts. Write dates the way people do "
            "('today', 'Friday'), never as YYYY-MM-DD. "
            'Reply JSON: {"subject": "...", "body": "..."}\n\n'
            f"Their original email:\nSubject: {src['subject']}\n{src['body'][:2500]}", "follow_up"),
            purpose=f"follow-up {row['id']}", json_mode=True, max_tokens=600)
        try:
            d = r.json()
        except Exception as e:
            _abstain("follow_up", row["text"], Verdict(False, [f"model reply unusable: {e}"]))
            continue
        v = shape(d, {"subject": str, "body": str})
        if v:
            v.merge(sendable_text(d["body"]))
            v.merge(honest_email(d["body"], recipient_first=name, owner_first=read_notes_owner().split(" ")[0],
                                 today=today))
        if not v:
            _abstain("follow_up", row["text"], v, d)
            continue
        req = approvals.propose(
            "send_email", {"to": to, "subject": d["subject"], "body": d["body"]},
            summary=f"Email {to}: \"{d['subject']}\"",
            why=(f"{full} promised: {row['text']} (due {row.get('due')}); {overdue} day(s) late." if theirs
                 else f"You promised: {row['text']} (due {row.get('due')})."),
            checks=["no template holes", f"greets {name}, not you", "no dates already passed", "length ok"],
            ledger_id=row["id"])
        if not req:
            continue
        ledger.touch(row["id"], f"drafted follow-up, waiting for approval {req['id']}")
        notify.ask(req)
        asked.append(req)
    return asked


def read_notes_owner() -> str:
    from .config import settings
    return settings.owner_name


def note(label: str, default: str = "") -> str:
    """A '- Label: value' line from notes.md. The business itself lives in the owner's notes, not in code,
    so the same Kept works for a web designer, a contractor or a bookkeeper."""
    m = re.search(rf"^-?\s*{re.escape(label)}:\s*(.+)$", read_notes(), re.I | re.M)
    return m.group(1).strip() if m else default


def business() -> str:
    return note("Business", "a one-person business")


# --------------------------------------------------------------------------- topics
def watch_topics(topics: list[str] | None = None) -> dict:
    """Tavily finds news; Super summarises; only claims that quote a fetched page survive."""
    from .tools import search

    topics = topics or [t.strip("- ").strip() for t in read_notes().split("## Watch")[-1].splitlines()
                        if t.strip().startswith("-")][:3]
    found = {"topics": topics, "claims": [], "dropped": 0}
    from .parallel import pmap

    for claims, dropped in pmap(lambda t: _watch_one(t, search), topics):
        found["claims"] += claims
        found["dropped"] += dropped
    write_json("watch.json", {"ts": now_iso(), **found})
    journal(f"Watched {len(topics)} topics: kept {len(found['claims'])} grounded facts, "
            f"dropped {found['dropped']} that I couldn't verify")
    return found


def _watch_one(topic: str, search) -> tuple[list[dict], int]:
    claims, dropped = [], 0
    try:
        results = search.search(topic, max_results=4)
    except Exception as e:
        _abstain("watch", topic, Verdict(False, [f"search failed: {e}"]))
        return claims, dropped
    if not results:
        return claims, dropped
    sources = {r["id"]: r["content"] for r in results}
    listing = "\n\n".join(f"[{r['id']}] {r['title']}\n{r['content'][:2500]}" for r in results)
    try:
        data = router.ask("plan", _msgs(
            f"The owner follows this topic: '{topic}'. From the sources below, give at most 2 facts "
            "that could change what a small business owner does this month (prices, rules, deadlines). "
            "Each fact must make sense on its own, without the article, and must quote the exact words "
            "from its source. Skip opinions and marketing. Reply JSON: "
            '{"claims": [{"text": "...", "source": "<id in brackets>", "quote": "exact words"}]}\n\n'
            + listing), purpose=f"watch '{topic}'", json_mode=True, max_tokens=700).json()
    except Exception as e:
        _abstain("watch", topic, Verdict(False, [f"model reply unusable: {e}"]))
        return claims, dropped
    for c in (data.get("claims") or [])[:3]:
        c["source"] = source_id(c.get("source"), sources)
        v = grounded([c], sources)
        if v:
            url = next(r["url"] for r in results if r["id"] == c["source"])
            claims.append({"topic": topic, "text": c["text"], "url": url, "quote": c["quote"]})
        else:
            dropped += 1
            _abstain("watch", c.get("text", topic)[:80], v, c)
    return claims, dropped


# --------------------------------------------------------------------------- hard call
def weigh_overload() -> dict | None:
    """When the week holds more promises than time, Ultra decides what to move and drafts
    the honest message. That message still needs the owner's Yes."""
    today = date.today()
    busy = {a.get("ledger_id") for a in approvals.pending()}
    # a promise that already has a message waiting for the owner's Yes is off the table:
    # two contradicting emails to the same person is worse than either one
    due_soon = [r for r in ledger.open_sorted(today) if r.get("due") and
                (date.fromisoformat(r["due"][:10]) - today).days <= 3]
    if len(due_soon) < 3:  # overload is about the week's load, counted over everything due
        return None
    soon = [r for r in due_soon if r.get("contact") and r["id"] not in busy]
    if not soon:
        return None
    mails = {m["id"]: m for m in mail.inbox(50)}

    def context(r: dict) -> str:
        src = mails.get(r.get("source", ""))
        return f"\n    their words: \"{src['body'][:600]}\"" if src else ""

    # the decision is only as good as what Ultra can see: give it the original words, not just a title
    listing = "\n".join(f"- [{r['id']}] {r['text']} | owed to {r.get('who')} | due {r['due']}{context(r)}"
                        for r in soon)
    r = router.ask("judge", _msgs(
        "These promises are all due within three days and the owner works alone. Pick the ONE whose "
        "deadline should move, considering who is affected, money at stake, and trust. Read each "
        "person's own words: never move something that they say has a hard deadline of their own "
        "(a filing date, a launch, a payment due), and never claim the delay has no impact on them. "
        "Draft a short, "
        f"honest note from {read_notes_owner()} to that person proposing a new date (greet them by first "
        f"name, write dates the way people do). Today is {today.isoformat()} ({today:%A}). Reply JSON: "
        '{"move_id": "<id>", "new_due": "YYYY-MM-DD", "reason": "...", '
        '"subject": "...", "body": "..."}\n\n' + listing), purpose="overload decision",
        json_mode=True, max_tokens=2500)  # recorded run: Ultra thought for 3,900 tokens and was cut off
    try:
        d = r.json()
    except Exception as e:
        _abstain("overload", "pick one to move", Verdict(False, [f"model reply unusable: {e}"]))
        return None
    ids = {x["id"]: x for x in soon}
    v = shape(d, {"move_id": str, "new_due": str, "reason": str, "subject": str, "body": str})
    if v:
        v.merge(one_of(d["move_id"], list(ids), "move_id"))
        v.merge(plausible_due(d["new_due"]))
        if v and d["new_due"][:10] <= ids[d["move_id"]]["due"][:10]:
            v.add(f"new date {d['new_due']} is not later than the current one")
        v.merge(sendable_text(d["body"]))
    if v:
        row = ids[d["move_id"]]
        v.merge(honest_email(d["body"], recipient_first=(row.get("who") or "").split(" ")[0],
                             owner_first=read_notes_owner().split(" ")[0], today=today))
    if not v:
        _abstain("overload", "pick one to move", v, d)
        return None
    to = row["contact"]  # the address comes from the original email, never from the model
    req = approvals.propose(
        "send_email", {"to": to, "subject": d["subject"], "body": d["body"]},
        summary=f"Ask {row.get('who')} to move '{row['text']}' to {d['new_due']}",
        why=d["reason"], checks=["picked from this week's promises", "new date is sane",
                                 "no template holes"], ledger_id=row["id"],
        reasoning=r.reasoning, model_label="Nemotron Ultra")
    if req:
        notify.ask(req)
    return req


# --------------------------------------------------------------------------- brief
def _cash_line() -> dict | None:
    from . import money
    f = money.forecast(30)
    if not f["short"]:
        return {"ok": True, "lowest_balance": f["lowest"]}
    return {"ok": False, "short_on": f["short"]["date"], "gap": f["short"]["gap"], "because": f["short"]["because"],
            "would_fix": [x["what"] for x in f.get("fix", [])]}


def morning_brief() -> dict:
    """Super writes the day; code makes sure nothing open is left out."""
    today = date.today()
    open_rows = ledger.open_sorted(today)
    watch = read_json("watch.json", {})
    pend = approvals.pending()
    row = lambda r: {"id": r["id"], "text": r["text"], "who": r.get("who"), "due": r.get("due"),
                     "overdue_days": ledger.days_overdue(r, today)}
    facts = {
        "you_owe": [row(r) for r in open_rows if ledger.direction(r) == "i_owe"][:12],
        "owed_to_you": [row(r) for r in open_rows if ledger.direction(r) == "owed_to_me"][:6],
        "waiting_for_your_yes": [{"id": a["id"], "summary": a["summary"]} for a in pend],
        "news": watch.get("claims", [])[:5],
        "cash": _cash_line(),
        "yesterday": read_journal(2)[-3000:],
    }
    r = router.ask("plan", _msgs(
        f"Write {read_notes_owner()}'s morning brief for {today.isoformat()} ({today:%A}). Order: what "
        f"{read_notes_owner()} owes that is overdue; money (if cash is short, say when and by how much); what "
        "others owe them; then ONE line saying how many messages wait for their Yes (don't list them). "
        f"The plan is three things {read_notes_owner()} does today, each taken from you_owe or "
        "owed_to_you, written as an action for them. Plain, short sentences. Reply JSON: "
        '{"headline": "...", "lines": [{"ref": "<ledger id or null>", "text": "..."}], '
        '"plan": [{"ref": "<ledger id>", "text": "..."}]}\n\nFacts:\n' + json.dumps(facts, ensure_ascii=False), "brief"),
        purpose="morning brief", json_mode=True, max_tokens=900)
    try:
        b = r.json()
        if isinstance(b, dict):
            b.setdefault("plan", [])  # a brief without a plan is still a brief
        v = shape(b, {"headline": str, "lines": list, "plan": list})
    except Exception as e:
        b, v = {}, Verdict(False, [f"model reply unusable: {e}"])
    if not v:
        _abstain("brief", "morning brief", v, b)
        b = {"headline": "Brief written by rules (the model reply did not pass checks)", "lines": [], "plan": []}
    facts["open"] = facts["you_owe"] + facts["owed_to_you"]
    known = {x["id"] for x in facts["open"]} | {x["id"] for x in facts["waiting_for_your_yes"]}
    # a plan step must point at something real; free-floating to-dos are how direction got flipped
    b["plan"] = [p for p in b["plan"] if isinstance(p, dict) and p.get("ref") in known][:3]
    b["lines"] = [ln for ln in b["lines"] if isinstance(ln, dict) and (ln.get("ref") in known or not ln.get("ref"))]
    mentioned = {ln.get("ref") for ln in b["lines"]}
    # the rule that makes the ledger trustworthy: an overdue promise is never silently skipped
    for x in facts["open"]:
        if x["overdue_days"] > 0 and x["id"] not in mentioned:
            b["lines"].insert(0, {"ref": x["id"], "text": f"Overdue {x['overdue_days']}d: {x['text']} ({x['who']})",
                                  "added_by": "rule"})
    b.update({"date": today.isoformat(), "model": r.model, "ts": now_iso()})
    write_json("brief.json", b)
    journal(f"Morning brief: {b['headline']}")
    notify.tell(b["headline"] + "\n\n" + "\n".join("• " + ln["text"] for ln in b["lines"][:8]))
    return b


def run_day() -> dict:
    """The whole loop, as the scheduler runs it each morning.

    1. read the inbox (each email in parallel): everything else depends on the ledger it fills
    2. follow-ups, money, rescue, growth, offers and news side by side: they read the ledger and
       the money book but don't depend on each other; one message per person is enforced
       atomically by the approval gate
    3. the overload call, then the brief, which reads what everyone else did
    """
    from concurrent.futures import ThreadPoolExecutor

    from . import checkins, followups, growth, money, offers, rescue
    out: dict[str, Any] = {}

    def guarded(name, fn):
        try:
            return fn()
        except BudgetExceeded as e:
            return f"stopped: {e}"
        except Exception as e:
            append_audit("job_failed", job=name, error=str(e)[:300])
            return f"failed: {type(e).__name__}: {e}"

    out["triage"] = guarded("triage", triage_inbox)
    if isinstance(out["triage"], str) and out["triage"].startswith("stopped"):
        return out
    middle = [("follow_ups", follow_ups), ("money", money.chase), ("rescue", rescue.plan),
              ("growth", growth.moments), ("offers", offers.propose), ("checkins", checkins.propose),
              ("quiet_leads", followups.propose), ("watch", watch_topics)]
    with ThreadPoolExecutor(max_workers=len(middle)) as ex:
        futures = {name: ex.submit(guarded, name, fn) for name, fn in middle}
        for name, f in futures.items():
            out[name] = f.result()
    from .reply import answer_new
    for name, fn in [("answers", answer_new), ("overload", weigh_overload), ("brief", morning_brief)]:
        out[name] = guarded(name, fn)
    return out
