"""Scope guard: notice when a client asks for work the agreement doesn't cover.

Unpaid "small extras" are where a one-person business quietly loses money. For every
client with an agreement on file (data/contracts/<email>.md), Kept reads each new
request in their mail and asks Nemotron Ultra one question: is this covered?

Ultra must quote the agreement to answer. Code checks the quote is really in the
agreement, prices the extra from the owner's own rate, and if anything is uncertain
Kept says so instead of guessing. An out-of-scope request becomes a friendly reply
offering the extra at a stated price, which waits for the owner's Yes like any email.
"""
from __future__ import annotations

import math
import re
from datetime import date
from pathlib import Path

from . import approvals, calibration, ledger
from .agent import _abstain, _msgs, read_notes_owner, sender
from .llm import router
from .store import data_dir, journal, locked, now_iso, read_json, read_notes, write_json
from .tools import notify
from .validators import Verdict, grounded, honest_email, one_of, sendable_text, shape

VERDICTS = ("in_scope", "out_of_scope", "unclear", "already_promised")


def contract_for(address: str) -> str:
    p = data_dir() / "contracts" / f"{address.lower()}.md"
    return p.read_text() if p.exists() else ""


def hourly_rate() -> float | None:
    m = re.search(r"hourly(?: rate)?[^$\d]*\$?\s*(\d+(?:\.\d+)?)", read_notes(), re.I)
    return float(m.group(1)) if m else None


def price_for(hours_low: float, hours_high: float, rate: float) -> int:
    """Midpoint of the estimate at the owner's rate, rounded up to $5."""
    return int(math.ceil((hours_low + hours_high) / 2 * rate / 5.0) * 5)


def review(m: dict) -> dict | None:
    """Returns {requests: [...], proposal: approval|None} or None if no agreement is on file."""
    name, addr = sender(m)
    agreement = contract_for(addr)
    if not agreement:
        return None
    rate = hourly_rate()
    # two independent reads; money is only asked for when both agree it isn't covered
    from .parallel import pmap
    # the two independent readings run side by side
    (first, r), (second, _) = pmap(lambda t: _judge(m, name, agreement, t), [0.2, 0.7])
    if first is None:
        return {"requests": [], "proposal": None}
    items = _reconcile(first, second or [])
    # promises the owner made earlier in this client's threads (not the request we're judging now)
    promised = [x for x in ledger.items("open") if (x.get("contact") or "").lower() == addr
                and x.get("source") != m["id"] and ledger.direction(x) == "i_owe"]
    checked = []
    sources = {"agreement": agreement, "email": m["subject"] + "\n" + m["body"]}
    for it in items[:6]:
        v = shape(it, {"request": str, "verdict": str, "agreement_quote": str, "email_quote": str})
        if v:
            v.merge(one_of(it["verdict"], VERDICTS, "verdict"))
            v.merge(grounded([{"source": "email", "quote": it["email_quote"]}], sources))
            if it["verdict"] != "unclear":
                v.merge(grounded([{"source": "agreement", "quote": it["agreement_quote"]}], sources))
        if v and it["verdict"] == "out_of_scope":
            need = min(2, len(_words(it["request"]))) or 1  # short requests ("add a blog page") have one key word
            already = next((x for x in promised if _overlap(it["request"], x["text"] + " " + x.get("quote", "")) >= need), None)
            if already:  # the owner already said yes to this in their own promise; don't sell it twice
                it["verdict"], it["reason"] = "already_promised", f"already in your promises: '{already['text']}'"
        if v and it["verdict"] == "out_of_scope":
            lo, hi = it.get("hours_low"), it.get("hours_high")
            if not all(isinstance(x, (int, float)) for x in (lo, hi)) or not (0 < lo <= hi <= 60):
                v.add(f"hours estimate {lo}-{hi} isn't a sane range")
            elif rate is None:
                v.add("no hourly rate in notes.md, so Kept can't price the extra")
            else:
                it["price"] = price_for(lo, hi, rate)
        if not v:
            _abstain("scope", it.get("request", m["subject"])[:80] if isinstance(it, dict) else m["subject"], v, it)
            continue
        checked.append({k: it.get(k) for k in ("request", "email_quote", "verdict", "agreement_quote",
                                                "reason", "hours_low", "hours_high", "price")})
    extras = [c for c in checked if c["verdict"] == "out_of_scope"]
    proposal = _offer(m, name, addr, checked, extras, r.reasoning, agreement) if extras else None
    with locked():
        rows = read_json("scope.json", [])
        rows.append({"ts": now_iso(), "mail": m["id"], "client": name, "subject": m["subject"],
                     "requests": checked, "approval": proposal["id"] if proposal else None, "model": r.model})
        write_json("scope.json", rows[-100:])
    journal(f"Scope check on '{m['subject']}' from {name}: "
            + ", ".join(f"{c['request']} -> {c['verdict']}" for c in checked))
    return {"requests": checked, "proposal": proposal}


_STOP = {"the", "and", "for", "with", "page", "with", "that", "this", "your", "from", "send", "make", "add"}


def _words(t: str) -> set[str]:
    return {w for w in re.findall(r"[a-z]{4,}", t.lower()) if w not in _STOP}


def _overlap(a: str, b: str) -> int:
    return len(_words(a) & _words(b))


def _judge(m: dict, name: str, agreement: str, temperature: float):
    r = router.ask("judge", _msgs(
        f"{name} is a client of {read_notes_owner()}. Below is their signed agreement and a new email from them. "
        "List each piece of WORK they ask for in the email (a page, a feature, a fix, a change). Ignore "
        "scheduling, questions and thanks. For each, decide whether the agreement already covers it: "
        "in_scope, out_of_scope, or unclear. Quote the exact words of the agreement that decide it, and the "
        "exact words of the email that make the request. For out_of_scope work, estimate the hours as a "
        "low/high range. If the agreement doesn't settle it, say unclear; do not guess.\n"
        'Reply JSON: {"requests": [{"request": "...", "email_quote": "...", "verdict": "in_scope|out_of_scope|unclear", '
        '"agreement_quote": "...", "reason": "one sentence", "hours_low": 0, "hours_high": 0}]}\n\n'
        f"AGREEMENT:\n{agreement[:6000]}\n\nEMAIL from {name}, subject '{m['subject']}':\n{m['body'][:4000]}"),
        purpose=f"scope check {m['id']} (read {'1' if temperature < 0.5 else '2'})", json_mode=True,
        max_tokens=1200, temperature=temperature)
    try:
        return [x for x in (r.json().get("requests") or []) if isinstance(x, dict)], r
    except Exception as e:
        _abstain("scope", m["subject"], Verdict(False, [f"model reply unusable: {e}"]))
        return None, r


def _reconcile(first: list[dict], second: list[dict]) -> list[dict]:
    """In a live run the same request ('make the logo bigger') was judged covered one time
    and extra the next. Where two reads disagree, Kept says 'unclear' and leaves it to you."""
    out = []
    for it in first:
        twin = max(second, key=lambda o: _overlap(str(o.get("email_quote", "")) + " " + str(o.get("request", "")),
                                                   str(it.get("email_quote", "")) + " " + str(it.get("request", ""))),
                   default=None)
        other = twin.get("verdict") if twin and _overlap(str(twin.get("email_quote", "")), str(it.get("email_quote", ""))) >= 2 else None
        if it.get("verdict") == "out_of_scope" and other != "out_of_scope":
            it = {**it, "verdict": "unclear",
                  "reason": f"two independent reads disagreed ({it.get('verdict')} vs {other or 'not listed'}); your call"}
        out.append(it)
    return out


def _offer(m, name, addr, checked, extras, reasoning, agreement="") -> dict | None:
    first = name.split(" ")[0]
    total = sum(e["price"] for e in extras)
    today = date.today()
    lines = "\n".join(f"- {e['request']}: ${e['price']} (about {e['hours_low']}-{e['hours_high']} hours)" for e in extras)
    covered = "\n".join(f"- {c['request']}" for c in checked if c["verdict"] == "in_scope") or "- (nothing else)"
    r = router.ask("draft", _msgs(
        f"Write a short, friendly email FROM {read_notes_owner()} TO {name}. Confirm the covered items will be "
        "done as part of the agreement. For the extra items, explain in one sentence that they're outside what "
        "you agreed, and offer each at the price below, written once as a plain number like $300. Ask if "
        "they'd like to go ahead. No pressure, no "
        f"legal tone. Greet {first} by first name, sign as {read_notes_owner()}. "
        'Reply JSON: {"subject": "...", "body": "..."}\n\n'
        f"Covered:\n{covered}\n\nExtras:\n{lines}\n\nTheir email:\n{m['body'][:2000]}", "follow_up"),
        purpose=f"scope offer {m['id']}", json_mode=True, max_tokens=700)
    try:
        d = r.json()
    except Exception as e:
        _abstain("scope", "offer", Verdict(False, [f"model reply unusable: {e}"]))
        return None
    v = shape(d, {"subject": str, "body": str})
    if v:
        v.merge(sendable_text(d["body"]))
        v.merge(honest_email(d["body"], recipient_first=first, owner_first=read_notes_owner().split(" ")[0], today=today))
        for e in extras:  # the price in the email must be the price code computed
            if f"${e['price']}" not in d["body"].replace(",", ""):
                v.add(f"the email doesn't state the computed price ${e['price']} for '{e['request']}'")
        known = {e["price"] for e in extras} | {total} | {int(x) for x in re.findall(r"\$(\d+)", agreement.replace(",", ""))}
        stray = {int(x) for x in re.findall(r"\$(\d+)", d["body"].replace(",", ""))} - known
        if stray:
            v.add(f"the email mentions prices code didn't compute: {sorted(stray)}")
    if not v:
        _abstain("scope", "offer", v, d)
        return None
    req = approvals.propose(
        "send_email", {"to": addr, "subject": d["subject"], "body": d["body"]},
        summary=f"Offer {name} the extra work for ${total}",
        why="Outside the signed agreement: " + "; ".join(f"{e['request']} (agreement: \"{e['agreement_quote'][:90]}\")"
                                                          for e in extras),
        checks=["every verdict quotes the agreement", "prices computed from your hourly rate",
                "no other prices in the email", f"greets {first}"],
        reasoning=reasoning, model_label="Nemotron Ultra")
    if req:
        notify.ask(req)
    return req
