"""Growth without spam: ask at the moment of delight, and let finished work speak.

No cold blasts and no automated DMs: those get accounts banned and make clients wary.
Instead Kept watches for two moments that already exist in the owner's week:

  * Delight. A client writes that they're happy, the work was delivered on time, they
    owe nothing overdue and the owner owes them nothing. That's when a review or a
    referral is easiest to give, so Kept drafts a short ask (Nemotron Super). If any of
    those conditions fails, it waits. Asking while a bug is still open is worse than
    not asking at all.
  * Finished work. The same moment becomes a short "what I built" post for LinkedIn
    or Instagram. Every number in the post must come from the client's own words or
    the owner's records, and a client is only named if notes.md says that's fine.

Both wait for the owner's Yes. In demo mode posts are written to data/outbox/posts.
"""
from __future__ import annotations

import json
import re
from datetime import date, datetime, timedelta

from . import approvals, calibration, ledger, media, money
from .agent import _abstain, _msgs, business, note, read_notes_owner, sender
from .llm import router
from .store import data_dir, journal, locked, now_iso, read_json, read_notes, write_json
from .tools import mail, notify
from .validators import Verdict, grounded, honest_email, sendable_text, shape

FILE = "growth.json"
ASK_EVERY_DAYS = 90


def _note(label: str) -> str:
    m = re.search(rf"{label}:\s*(.+)", read_notes(), re.I)
    return m.group(1).strip() if m else ""


def nameable() -> list[str]:
    return [x.strip() for x in _note("Clients I may name in posts").split(",") if x.strip()]


def not_now(client: str, contact: str, today: date) -> str | None:
    """The reasons to wait, checked by code."""
    book = money.load()
    if any(i["client"] == client and not i.get("paid_on") and datetime.fromisoformat(i["due"]).date() < today
           for i in book["invoices"]):
        return "they owe an overdue invoice"
    if any(i["client"] == client and not i.get("paid_on") for i in book["invoices"]):
        return "the project isn't finished and paid yet"
    mine = [r for r in ledger.open_sorted(today, which="i_owe") if (r.get("contact") or "").lower() == contact]
    if any(ledger.days_overdue(r, today) > 0 for r in mine):
        return "you owe them something overdue"
    if mine:
        return "there is still open work for them"
    done = [r for r in ledger.items() if r["status"] == "done" and (r.get("contact") or "").lower() == contact
            and calibration.slip_days(r) is not None]
    if done and calibration.slip_days(sorted(done, key=lambda r: r["closed"])[-1]) > 0:
        return "the last thing you delivered them was late"
    asked = [g for g in read_json(FILE, []) if g["client"] == client and g["kind"] == "ask"
             and (today - datetime.fromisoformat(g["ts"][:10]).date()).days < ASK_EVERY_DAYS]
    if asked:
        return f"you asked them in the last {ASK_EVERY_DAYS} days"
    return None


def moments(today: date | None = None, only: list[dict] | None = None) -> dict:
    """only: look at just these emails (a judge's own message in the demo) and leave the
    morning's growth summary alone."""
    today = today or date.today()
    clients = {i["contact"].lower(): i["client"] for i in money.load()["invoices"]}
    out = {"asks": [], "posts": [], "waiting": []}
    recent = []
    for m in (only if only is not None else mail.inbox(50)):
        name, addr = sender(m)
        if addr not in clients:
            continue
        try:
            when = datetime.fromisoformat(str(m.get("date"))[:10]).date()
            if (today - when).days > 10:
                continue
        except ValueError:
            pass
        recent.append(m)

    def delight(m):
        r = router.ask("classify", _msgs(
            "Is this client clearly delighted with finished work (praise, thanks, a good result)? If yes, copy the "
            'exact words that show it. Reply JSON: {"delighted": true|false, "quote": "exact words or empty"}\n\n'
            f"From: {m['from']}\n\n{m['body'][:2500]}"), purpose=f"delight? {m['id']}", json_mode=True, max_tokens=150)
        try:
            return r.json()
        except Exception:
            return None

    from .parallel import pmap
    for m, d in zip(recent, pmap(delight, recent)):
        name, addr = sender(m)
        if not d:
            continue
        if not d.get("delighted"):
            continue
        v = grounded([{"source": "m", "quote": d.get("quote", "")}], {"m": m["body"]})
        if not v:
            _abstain("growth", m["subject"], v, d)
            continue
        client = clients[addr]
        why_not = not_now(client, addr, today)
        if why_not:
            out["waiting"].append({"client": client, "why": why_not, "quote": d["quote"]})
            journal(f"{client} sounds happy, but not asking yet: {why_not}")
            continue
        ask = _ask(client, addr, m, d["quote"])
        if ask:
            out["asks"].append(ask["id"])
        post = _post(client, m)
        if post:
            out["posts"].append(post["id"])
    if only is None:
        write_json("growth_last.json", {"ts": now_iso(), **out})
    return out


def _ask(client: str, addr: str, m: dict, quote: str) -> dict | None:
    first = client.split(" ")[0]
    link = _note("Review link")
    r = router.ask("draft", _msgs(
        f"{client} just wrote: \"{quote}\". Write a short reply FROM {read_notes_owner()} TO {first}: thank them "
        "warmly and specifically, then ask, once and lightly, if they'd leave a short review"
        + (f" at {link}" if link else "") + f" or mention {read_notes_owner()} to someone who needs {note('What new clients need', 'the same kind of work')}. "
        f"No discount, no pressure. Greet {first}, sign as {read_notes_owner()}. Under 90 words. "
        'Reply JSON: {"subject": "...", "body": "..."}', "follow_up"), purpose=f"review ask {client}",
        json_mode=True, max_tokens=400)
    try:
        e = r.json()
    except Exception as ex:
        _abstain("growth", client, Verdict(False, [f"model reply unusable: {ex}"]))
        return None
    v = shape(e, {"subject": str, "body": str})
    if v:
        v.merge(sendable_text(e["body"], max_chars=800))
        v.merge(honest_email(e["body"], recipient_first=first, owner_first=read_notes_owner().split(" ")[0]))
        if link and link not in e["body"]:
            v.add("the review link is missing or changed")
        urls = set(re.findall(r"https?://\S+", e["body"])) - {link, link + ".", link + ","}
        if urls:
            v.add(f"the email has links that aren't yours: {sorted(urls)[:2]}")
        if re.search(r"\b(discount|% off|gift card|free)\b", e["body"], re.I):
            v.add("offering something in exchange for a review isn't allowed on most review sites")
    if not v:
        _abstain("growth", client, v, e)
        return None
    req = approvals.propose("send_email", {"to": addr, "subject": e["subject"], "body": e["body"]},
                            summary=f"Ask {client} for a review while they're happy",
                            why=f"They wrote: \"{quote[:120]}\". Delivered on time, nothing owed either way.",
                            checks=["only your review link", "nothing offered in exchange", f"greets {first}"])
    if req:
        with locked():
            rows = read_json(FILE, [])
            rows.append({"client": client, "kind": "ask", "ts": now_iso(), "approval": req["id"]})
            write_json(FILE, rows)
        notify.ask(req)
    return req


def _post(client: str, m: dict) -> dict | None:
    allowed = [n for n in nameable() if n.lower().split(" ")[0] in (m["from"] + m["body"]).lower()]
    pics = media.pair(client)
    facts = {"client_words": m["body"], "may_name": allowed[0] if allowed else None,
             "has_before_and_after_pictures": "before" in pics and "after" in pics,
             "work": [r["text"] for r in ledger.items() if r["status"] == "done" and
                      (r.get("contact") or "").lower() == sender(m)[1]][-3:]}
    r = router.ask("draft", _msgs(
        f"Write a short LinkedIn post (under 120 words) by {read_notes_owner()}, who runs {business()}, about "
        "finished work. Use ONLY these facts. If may_name is null, don't name the client; describe them "
        "('a local coffee shop'). If there are before and after pictures, the post introduces them in one "
        "line (they're attached). No hashtags beyond two, no emojis beyond one, no invented numbers. "
        'Reply JSON: {"text": "..."}\n\nFacts:\n' + json.dumps(facts, ensure_ascii=False)),
        purpose=f"proof-of-work post {client}", json_mode=True, max_tokens=500)
    try:
        text = r.json().get("text", "")
    except Exception as ex:
        _abstain("growth", f"post {client}", Verdict(False, [f"model reply unusable: {ex}"]))
        return None
    v = sendable_text(text, max_chars=1100)
    source_text = m["body"] + " " + " ".join(facts["work"])
    nums = set(re.findall(r"\b\d+(?:[.,]\d+)?%?", text))
    words_nums = {"two": "2", "three": "3", "four": "4", "five": "5"}
    known = set(re.findall(r"\b\d+(?:[.,]\d+)?%?", source_text)) | {v_ for k, v_ in words_nums.items() if k in source_text.lower()}
    if nums - known:
        v.add(f"the post has numbers that aren't in your records: {sorted(nums - known)}")
    if not allowed and re.search(re.escape(client.split(" ")[-1]), text, re.I):
        v.add(f"the post names {client}, but notes.md doesn't allow it")
    if not v:
        _abstain("growth", f"post {client}", v, {"text": text})
        return None
    images = [pics[w]["path"] for w in ("before", "after") if w in pics]
    req = approvals.propose("publish_post", {"platform": "linkedin", "text": text, "images": images},
                            summary=f"Post about the {client.split(' ')[-1]} project on LinkedIn",
                            why="Finished work your client is happy with is the best advertising you have.",
                            checks=["every number comes from your records or their email",
                                    "client named only if you allowed it in notes.md"])
    if req:
        notify.ask(req)
    return req


@approvals.action("publish_post", needs_approval=True)
def publish_post(args: dict) -> str:
    out = data_dir() / "outbox" / "posts"
    out.mkdir(parents=True, exist_ok=True)
    f = out / f"{now_iso().replace(':', '-')}_{args.get('platform', 'post')}.json"
    f.write_text(json.dumps({**args, "ts": now_iso(), "note": "demo mode: saved, not posted"}, indent=1))
    journal(f"Saved a {args.get('platform')} post to outbox")
    return f"demo: saved to outbox/posts/{f.name}"
