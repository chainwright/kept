"""What Kept actually does. Each job follows the same loop:

    gather facts -> a Nemotron model proposes -> code verifies -> act, ask, or abstain

Local bookkeeping (adding to the ledger, writing the journal) happens on its own.
Anything that reaches another person goes through the approval gate.
"""
from __future__ import annotations

import json
from datetime import date
from typing import Any

from . import approvals, ledger
from .config import ROOT
from .llm import BudgetExceeded, router
from .store import append_audit, journal, now_iso, read_journal, read_json, read_notes, write_json
from .tools import mail, notify
from email.utils import parseaddr

from .validators import Verdict, grounded, honest_email, one_of, plausible_due, sendable_text, shape

SYSTEM = ("You are Kept, an operator for a one-person business. You are careful and plain-spoken. "
          "You never invent facts. When asked for JSON, reply with JSON only.")


SKILLS = ROOT / "skills"


def skill(name: str) -> str:
    """Skills are plain markdown the owner can edit; they travel with every prompt that uses them."""
    p = SKILLS / f"{name}.md"
    return p.read_text().strip() if p.exists() else ""


def _msgs(user: str, skill_name: str | None = None) -> list[dict]:
    system = SYSTEM + ("\n\n" + skill(skill_name) if skill_name else "")
    return [{"role": "system", "content": system}, {"role": "user", "content": user}]


def _abstain(job: str, subject: str, verdict: Verdict, payload: Any = None) -> dict:
    rec = {"ts": now_iso(), "job": job, "subject": subject, "problems": verdict.problems,
           "payload": payload}
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
    """Sort new mail (Nano) and pull out anything the owner promised (Nano + checks)."""
    seen = set(read_json("seen_mail.json", []))
    new = [m for m in mail.inbox(50) if m["id"] not in seen]
    report = {"new": len(new), "commitments": [], "abstained": 0, "labels": {}}
    for m in new:
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
            report["abstained"] += 1
            continue
        v = shape(cls, {"kind": str, "needs_reply": bool, "one_line": str})
        v.merge(one_of(cls.get("kind"), ["lead", "client", "bill", "personal", "noise"], "kind"))
        if not v:
            _abstain("triage", m["subject"], v, cls)
            report["abstained"] += 1
            continue
        report["labels"][m["id"]] = cls
        if cls["kind"] != "noise":
            report["commitments"] += _extract_commitments(m)
        seen.add(m["id"])
    write_json("seen_mail.json", sorted(seen))
    labels = read_json("labels.json", {})
    labels.update(report["labels"])
    write_json("labels.json", labels)
    journal(f"Triaged {report['new']} new emails, found {len(report['commitments'])} commitments")
    return report


def _extract_commitments(m: dict) -> list[dict]:
    """Promises the OWNER made (or was asked to make) in this thread, each with proof."""
    out = []
    try:
        data = router.ask("extract", _msgs(
            f"This email was sent TO the business owner, {read_notes_owner()}, BY {sender(m)[0]}. "
            f"List things {read_notes_owner()} promised or must do for {sender(m)[0]}. Write each as a short "
            f"instruction to {read_notes_owner()}, naming the person (e.g. 'Send Maria the revised quote'). "
            "For each, copy the exact words from the email that show it. Reply JSON: "
            '{"items": [{"text": "short instruction", "due": "YYYY-MM-DD or null", '
            '"quote": "exact words from the email"}]}. '
            f"Today is {date.today().isoformat()} ({date.today():%A}). If there are none, return an empty list.\n\n"
            f"From: {m['from']}\nSubject: {m['subject']}\n\n{m['body'][:4000]}", "extract"),
            purpose=f"extract {m['id']}", json_mode=True, max_tokens=500).json()
    except Exception as e:
        _abstain("extract", m["subject"], Verdict(False, [f"model reply unusable: {e}"]))
        return out
    for it in (data.get("items") or [])[:5]:
        v = shape(it, {"text": str, "quote": str})
        v.merge(grounded([{"source": m["id"], "quote": it.get("quote", "")}],
                         {m["id"]: m["subject"] + "\n" + m["body"]}))
        v.merge(plausible_due(it.get("due")))
        if not v:
            _abstain("extract", it.get("text", m["subject"]), v, it)
            continue
        name, addr = sender(m)
        text = it["text"].strip()
        out.append(ledger.add(text[:1].upper() + text[1:], who=name, contact=addr, due=it.get("due"),
                              source=m["id"], origin="inbox"))
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
        due_soon = row.get("due") and row["due"][:10] <= today.isoformat()
        src = mails.get(row.get("source", ""))
        if not (due_soon and src):
            continue
        full, to = sender(src)
        name = full.split(" ")[0]
        overdue = ledger.days_overdue(row, today)
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
            why=f"You promised: {row['text']} (due {row.get('due')}).",
            checks=["no template holes", f"greets {name}, not you", "no dates already passed", "length ok"],
            ledger_id=row["id"])
        ledger.touch(row["id"], f"drafted follow-up, waiting for approval {req['id']}")
        notify.ask(req)
        asked.append(req)
    return asked


def read_notes_owner() -> str:
    from .config import settings
    return settings.owner_name


# --------------------------------------------------------------------------- topics
def watch_topics(topics: list[str] | None = None) -> dict:
    """Tavily finds news; Super summarises; only claims that quote a fetched page survive."""
    from .tools import search

    topics = topics or [t.strip("- ").strip() for t in read_notes().split("## Watch")[-1].splitlines()
                        if t.strip().startswith("-")][:3]
    found = {"topics": topics, "claims": [], "dropped": 0}
    for topic in topics:
        try:
            results = search.search(topic, max_results=4)
        except Exception as e:
            _abstain("watch", topic, Verdict(False, [f"search failed: {e}"]))
            continue
        if not results:
            continue
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
            continue
        for c in (data.get("claims") or [])[:3]:
            c["source"] = str(c.get("source", "")).strip().strip("[]").strip()
            v = grounded([c], sources)
            if v:
                url = next(r["url"] for r in results if r["id"] == c["source"])
                found["claims"].append({"topic": topic, "text": c["text"], "url": url, "quote": c["quote"]})
            else:
                found["dropped"] += 1
                _abstain("watch", c.get("text", topic)[:80], v, c)
    write_json("watch.json", {"ts": now_iso(), **found})
    journal(f"Watched {len(topics)} topics: kept {len(found['claims'])} grounded facts, "
            f"dropped {found['dropped']} that I couldn't verify")
    return found


# --------------------------------------------------------------------------- hard call
def weigh_overload() -> dict | None:
    """When the week holds more promises than time, Ultra decides what to move and drafts
    the honest message. That message still needs the owner's Yes."""
    today = date.today()
    busy = {a.get("ledger_id") for a in approvals.pending()}
    # a promise that already has a message waiting for the owner's Yes is off the table:
    # two contradicting emails to the same person is worse than either one
    soon = [r for r in ledger.open_sorted(today) if r.get("due") and r.get("contact") and
            r["id"] not in busy and (date.fromisoformat(r["due"][:10]) - today).days <= 3]
    if len(soon) < 3:
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
        json_mode=True, max_tokens=900)
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
                                 "no template holes"], ledger_id=row["id"])
    notify.ask(req)
    return req


# --------------------------------------------------------------------------- brief
def morning_brief() -> dict:
    """Super writes the day; code makes sure nothing open is left out."""
    today = date.today()
    open_rows = ledger.open_sorted(today)
    watch = read_json("watch.json", {})
    pend = approvals.pending()
    facts = {
        "open": [{"id": r["id"], "text": r["text"], "who": r.get("who"), "due": r.get("due"),
                  "overdue_days": ledger.days_overdue(r, today)} for r in open_rows[:15]],
        "waiting_for_your_yes": [{"id": a["id"], "summary": a["summary"]} for a in pend],
        "news": watch.get("claims", [])[:5],
        "yesterday": read_journal(2)[-3000:],
    }
    r = router.ask("plan", _msgs(
        f"Write {read_notes_owner()}'s morning brief for {today.isoformat()}. Start with what is overdue. "
        "Plain, short sentences. Reply JSON: "
        '{"headline": "...", "lines": [{"ref": "<ledger id or approval id or null>", "text": "..."}], '
        '"plan": ["three concrete things to do today"]}\n\nFacts:\n' + json.dumps(facts, ensure_ascii=False), "brief"),
        purpose="morning brief", json_mode=True, max_tokens=900)
    try:
        b = r.json()
        v = shape(b, {"headline": str, "lines": list, "plan": list})
    except Exception as e:
        b, v = {}, Verdict(False, [f"model reply unusable: {e}"])
    if not v:
        _abstain("brief", "morning brief", v, b)
        b = {"headline": "Brief written by rules (the model reply did not pass checks)", "lines": [], "plan": []}
    known = {x["id"] for x in facts["open"]} | {x["id"] for x in facts["waiting_for_your_yes"]}
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
    """The whole loop, as the scheduler runs it each morning."""
    out: dict[str, Any] = {}
    for name, fn in [("triage", triage_inbox), ("follow_ups", follow_ups), ("watch", watch_topics),
                     ("overload", weigh_overload), ("brief", morning_brief)]:
        try:
            out[name] = fn()
        except BudgetExceeded as e:
            out[name] = f"stopped: {e}"
            break
        except Exception as e:
            out[name] = f"failed: {type(e).__name__}: {e}"
            append_audit("job_failed", job=name, error=str(e)[:300])
    return out
