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
from .validators import Verdict, grounded, one_of, plausible_due, sendable_text, shape

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
            "List promises the business owner made or agreed to in this email thread "
            "(things THEY must do), and requests they must answer. For each, copy the exact "
            "words from the email that show it. Reply JSON: "
            '{"items": [{"text": "what must be done, short", "who": "person it is owed to", '
            '"due": "YYYY-MM-DD or null", "quote": "exact words from the email"}]}. '
            f"Today is {date.today().isoformat()}. If there are none, return an empty list.\n\n"
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
        out.append(ledger.add(it["text"], who=it.get("who") or m["from"], due=it.get("due"),
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
        due_soon = row.get("due") and row["due"][:10] <= today.isoformat()
        src = mails.get(row.get("source", ""))
        if not (due_soon and src):
            continue
        to = src["from"].split("<")[-1].rstrip(">").strip()
        name = row.get("who", "").split("<")[0].strip().split(" ")[0]
        r = router.ask("draft", _msgs(
            f"Write a short, warm, human email from {read_notes_owner()} to {row.get('who')} about this "
            f"commitment: '{row['text']}' (due {row.get('due')}). Be honest about status; do not promise "
            "anything new and do not invent facts. Use their first name. No placeholders. "
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
            v.merge(sendable_text(d["body"], must_mention=[name] if name else []))
        if not v:
            _abstain("follow_up", row["text"], v, d)
            continue
        req = approvals.propose(
            "send_email", {"to": to, "subject": d["subject"], "body": d["body"]},
            summary=f"Email {to}: \"{d['subject']}\"",
            why=f"You promised: {row['text']} (due {row.get('due')}).",
            checks=["no template holes", f"addresses {name or 'them'} by name", "length ok"],
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
                f"The owner follows this topic: '{topic}'. From the sources below, give at most 3 facts "
                "that matter to a small business owner this week. Each fact must quote the exact words "
                "from its source. Reply JSON: "
                '{"claims": [{"text": "...", "source": "<id in brackets>", "quote": "exact words"}]}\n\n'
                + listing), purpose=f"watch '{topic}'", json_mode=True, max_tokens=700).json()
        except Exception as e:
            _abstain("watch", topic, Verdict(False, [f"model reply unusable: {e}"]))
            continue
        for c in (data.get("claims") or [])[:3]:
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
    soon = [r for r in ledger.open_sorted(today) if r.get("due") and
            (date.fromisoformat(r["due"][:10]) - today).days <= 3]
    if len(soon) < 3:
        return None
    listing = "\n".join(f"- [{r['id']}] {r['text']} | owed to {r.get('who')} | due {r['due']}" for r in soon)
    r = router.ask("judge", _msgs(
        "These promises are all due within three days and the owner works alone. Pick the ONE whose "
        "deadline should move, considering who is affected, money at stake, and trust. Draft a short, "
        "honest note proposing a new date. Reply JSON: "
        '{"move_id": "<id>", "new_due": "YYYY-MM-DD", "reason": "...", "to": "<email>", '
        '"subject": "...", "body": "..."}\n\n' + listing), purpose="overload decision",
        json_mode=True, max_tokens=900)
    try:
        d = r.json()
    except Exception as e:
        _abstain("overload", "pick one to move", Verdict(False, [f"model reply unusable: {e}"]))
        return None
    ids = {x["id"]: x for x in soon}
    v = shape(d, {"move_id": str, "new_due": str, "reason": str, "to": str, "subject": str, "body": str})
    if v:
        v.merge(one_of(d["move_id"], list(ids), "move_id"))
        v.merge(plausible_due(d["new_due"]))
        v.merge(sendable_text(d["body"]))
        if "@" not in d["to"]:
            v.add(f"'{d['to']}' is not an email address")
    if not v:
        _abstain("overload", "pick one to move", v, d)
        return None
    row = ids[d["move_id"]]
    req = approvals.propose(
        "send_email", {"to": d["to"], "subject": d["subject"], "body": d["body"]},
        summary=f"Ask {d['to']} to move '{row['text']}' to {d['new_due']}",
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
