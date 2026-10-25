"""Rescue plan: when the cash forecast shows a gap, find the fastest honest ways to close it.

Kept gathers candidates from what it already knows, by code:
  - extra work already offered and waiting for the owner's Yes (exact price),
  - unpaid invoices that would close the gap if they arrived on time,
  - open leads the owner owes a reply to,
  - people who got a quote but never hired (re-engagement),
  - new local businesses found on the web through Tavily (verified prospects).
Nemotron Ultra ranks them by money, likelihood and speed, and code checks every step
it picks is a real candidate with the amount code computed. Emails to past contacts
are drafted for the owner's Yes; new prospects become lead cards, never cold emails.
"""
from __future__ import annotations

import json
import re
import statistics
from datetime import date, datetime, timedelta

from . import approvals, ledger, money
from .agent import _abstain, _msgs, business, note, read_notes_owner
from .llm import router
from .store import journal, now_iso, read_json, read_notes, write_json
from .tools import notify
from .validators import Verdict, dollar_amounts, grounded, honest_email, sendable_text, shape, source_id

DORMANT_DAYS = 21


def typical_project() -> int:
    amounts = [i["amount"] for i in money.load()["invoices"]]
    return int(statistics.median(amounts)) if amounts else 0


def candidates(today: date | None = None) -> list[dict]:
    today = today or date.today()
    out = []
    for a in approvals.pending():
        m = re.search(r"\$([\d,]+)", a["summary"])
        if a["kind"] == "send_email" and m and "extra work" in a["summary"]:
            out.append({"id": f"offer:{a['id']}", "type": "extra work waiting for your Yes", "who": a["args"]["to"],
                        "amount": int(m.group(1).replace(",", "")), "days_to_cash": 10, "detail": a["summary"]})
    f = money.forecast(30, today)
    for fx in f.get("fix", []):
        out.append({"id": f"invoice:{fx['invoice']}", "type": "overdue invoice", "who": fx["what"],
                    "amount": fx["amount"], "days_to_cash": 3,
                    "detail": f"due {fx['due']}, expected {fx['expected']} at this client's usual pace"})
    proj = typical_project()
    for r in ledger.open_sorted(today, which="i_owe"):
        labels = read_json("labels.json", {})
        if labels.get(r.get("source", ""), {}).get("kind") == "lead":
            out.append({"id": f"lead:{r['id']}", "type": "open lead waiting on you", "who": r.get("who"),
                        "amount": proj, "days_to_cash": 21, "detail": r["text"], "contact": r.get("contact")})
    hired = {i["client"] for i in money.load()["invoices"]}
    quoted = {}
    for r in ledger.items():
        if r["status"] == "done" and re.search(r"\b(quote|estimate|rates)\b", r["text"], re.I) and r.get("contact"):
            quoted[r["who"]] = r
    for who, r in quoted.items():
        last = datetime.fromisoformat(r["closed"][:10]).date()
        if who not in hired and (today - last).days >= DORMANT_DAYS:
            out.append({"id": f"revive:{r['id']}", "type": "quoted but never hired", "who": who,
                        "amount": proj, "days_to_cash": 30, "contact": r["contact"],
                        "detail": f"{r['text']} ({(today - last).days} days ago)"})
    return out


def find_prospects(limit: int = 3) -> list[dict]:
    """New local businesses that may need what the owner does, each backed by a page Kept fetched."""
    from .tools import search

    notes = read_notes()
    city = (re.search(r"\bin ([A-Z][a-z]+(?:,? [A-Z][a-z]+)*)", notes) or [None, ""])[1]
    if not city:
        return []
    try:
        results = search.search(note("Look for new clients", f"new small business opening {city}").replace("{city}", city),
                                max_results=6, days=60)
    except Exception as e:
        _abstain("prospects", city, Verdict(False, [f"search failed: {e}"]))
        return []
    if not results:
        return []
    sources = {r["id"]: r["content"] for r in results}
    listing = "\n\n".join(f"[{r['id']}] {r['title']}\n{r['content'][:2000]}" for r in results)
    r = router.ask("plan", _msgs(
        f"{read_notes_owner()} runs {business()} in {city}. From these pages, pick up to {limit} specific "
        f"businesses or people that plausibly need {note('What new clients need', 'this kind of work')} soon. For each, "
        "quote the exact words that show it, and write one friendly first line Alex could open with. "
        'Reply JSON: {"prospects": [{"business": "...", "why": "...", "source": "<id>", "quote": "exact words", '
        '"opener": "..."}]}\n\n' + listing), purpose="find prospects", json_mode=True, max_tokens=900)
    try:
        items = r.json().get("prospects") or []
    except Exception as e:
        _abstain("prospects", city, Verdict(False, [f"model reply unusable: {e}"]))
        return []
    out = []
    for p in items[:limit]:
        p["source"] = source_id(p.get("source"), sources)
        v = shape(p, {"business": str, "quote": str, "opener": str})
        if v:
            v.merge(grounded([p], sources))
            if p["business"].lower()[:12] not in sources.get(p["source"], "").lower():
                v.add(f"'{p['business']}' isn't named on the page it cites")
        if not v:
            _abstain("prospects", str(p.get("business", "?"))[:60], v, p)
            continue
        url = next(x["url"] for x in results if x["id"] == p["source"])
        out.append({"business": p["business"], "why": p.get("why", ""), "quote": p["quote"],
                    "opener": p["opener"], "url": url})
    return out


def plan(today: date | None = None) -> dict | None:
    today = today or date.today()
    f = money.forecast(30, today)
    if not f["short"]:
        write_json("rescue.json", {"ts": now_iso(), "needed": False, "lowest": f["lowest"]})
        return None
    cands = candidates(today)
    prospects = find_prospects()
    for i, p in enumerate(prospects):
        cands.append({"id": f"prospect:{i}", "type": "new local business (lead card)", "who": p["business"],
                      "amount": typical_project(), "days_to_cash": 45, "detail": p["why"]})
    gap = f["short"]
    r = router.ask("judge", _msgs(
        f"{read_notes_owner()} will be ${gap['gap']:.0f} short on {gap['date']} ({gap['because']}). Rank the "
        "candidates below by how likely and how fast they bring money, and pick the steps that close the gap "
        "first, then the ones that build next month. Use only the candidate ids given; don't invent amounts. "
        'Reply JSON: {"steps": [{"id": "<candidate id>", "action": "what Alex does, one line", "why": "one line"}]}'
        "\n\nCandidates:\n" + json.dumps(cands, ensure_ascii=False)), purpose="rescue plan",
        json_mode=True, max_tokens=1200)
    try:
        steps = r.json().get("steps") or []
    except Exception as e:
        _abstain("rescue", "plan", Verdict(False, [f"model reply unusable: {e}"]))
        steps = []
    by_id = {c["id"]: c for c in cands}
    chosen, seen = [], set()
    for s in steps:
        if not isinstance(s, dict) or s.get("id") not in by_id or s["id"] in seen:
            if isinstance(s, dict):
                _abstain("rescue", str(s.get("id")), Verdict(False, [f"step '{s.get('id')}' isn't one of the candidates"]), s)
            continue
        seen.add(s["id"])
        c = by_id[s["id"]]
        chosen.append({**c, "action": s.get("action", ""), "why": s.get("why", "")})
    covered, running = None, 0
    for c in chosen:
        if c["days_to_cash"] <= (datetime.fromisoformat(gap["date"]).date() - today).days + 7:
            running += c["amount"]
            if covered is None and running >= gap["gap"]:
                covered = c["id"]
    drafts = []
    for c in chosen:  # two check-ins at most: a pile of approvals is its own kind of noise
        if c["type"] == "quoted but never hired" and len(drafts) < 2:
            drafts.append(_reengage(c))
    ad = _ad_plan(gap, today)
    out = {"ts": now_iso(), "needed": True, "gap": gap, "steps": chosen, "prospects": prospects,
           "closes_gap_at": covered, "drafts": [d["id"] for d in drafts if d], "model": r.model,
           "reasoning": r.reasoning[:3000], "ad": ad["id"] if ad else None}
    write_json("rescue.json", out)
    journal(f"Rescue plan for a ${gap['gap']:.0f} gap on {gap['date']}: {len(chosen)} steps, "
            f"{len(prospects)} new prospects")
    return out


def _reengage(c: dict) -> dict | None:
    first = c["who"].split(" ")[0]
    r = router.ask("draft", _msgs(
        f"Write a short, warm check-in FROM {read_notes_owner()} TO {c['who']}, who got a quote "
        f"({c['detail']}) and didn't go ahead. No pressure, no discount, no guilt: ask if the project is "
        "still on their mind and offer a quick call. Greet them by first name, sign as "
        f"{read_notes_owner()}. Under 80 words. "
        'Reply JSON: {"subject": "...", "body": "..."}', "follow_up"),
        purpose=f"re-engage {c['who']}", json_mode=True, max_tokens=400)
    try:
        d = r.json()
    except Exception as e:
        _abstain("rescue", c["who"], Verdict(False, [f"model reply unusable: {e}"]))
        return None
    v = shape(d, {"subject": str, "body": str})
    if v:
        v.merge(sendable_text(d["body"], max_chars=700))
        v.merge(honest_email(d["body"], recipient_first=first, owner_first=read_notes_owner().split(" ")[0]))
        if re.search(r"\b(discount|\d+% off|deal|limited time)\b", d["body"], re.I):
            v.add("the check-in offers a discount; that's the owner's call, not Kept's")
    if not v:
        _abstain("rescue", c["who"], v, d)
        return None
    req = approvals.propose("send_email", {"to": c["contact"], "subject": d["subject"], "body": d["body"]},
                            summary=f"Check in with {c['who']} about their old quote",
                            why=f"Part of the plan to close the cash gap: {c['detail']}.",
                            checks=["no discount offered", f"greets {first}", "under 80 words"])
    if req:
        notify.ask(req)
    return req


def _ad_rules() -> dict | None:
    from .agent import note
    budget = note("Ad budget")
    m_day, m_days = re.search(r"\$(\d+) a day", budget), re.search(r"at most (\d+) days", budget)
    if not (m_day and m_days):
        return None
    return {"per_day": int(m_day.group(1)), "days": int(m_days.group(1)),
            "places": note("Ad places"), "audience": note("Ad audience")}


def _ad_plan(gap: dict, today: date) -> dict | None:
    """When the month runs short: a small paid boost for the best before/after work, as a plan for Alex's Yes.
    Budget and audience come from the owner's own rules; Kept never starts an ad itself."""
    from . import media
    from .growth import nameable
    rules = _ad_rules()
    if not rules:
        return None
    pairs = {c: p for c, p in (read_json("media.json", {}) or {}).items() if "before" in p and "after" in p}
    if not pairs:
        return None
    slug, pics = next(iter(pairs.items()))
    client = next((c for c in nameable() if media.slug(c) in slug or slug in media.slug(c)), None)
    total = rules["per_day"] * rules["days"]
    proj = typical_project()
    r = router.ask("draft", _msgs(
        f"{read_notes_owner()} runs {business()} and will be ${gap['gap']:.0f} short on {gap['date']} "
        f"({gap['because']}). Write a short local ad for a before/after photo of finished work"
        + (f" ({client})" if client else " (don't name the client)") + ": a headline under 8 words and two sentences "
        "of text, plain and specific, inviting people to send a photo of their kitchen for a free estimate. The headline "
        "and text are what strangers see: never mention Alex's cash, the gap, the ad budget or a typical job price, and no "
        "urgency ('limited time', 'act now', 'today only'). Then one sentence FOR "
        f"{read_notes_owner()} ONLY (why_now) on why a small boost makes sense now; there you may use the gap "
        f"${gap['gap']:.0f}, the budget ${rules['per_day']} a day for {rules['days']} days (${total}) and a typical job "
        f"about ${proj:,}. Reply JSON: " + '{"headline": "...", "text": "...", "why_now": "..."}'),
        purpose="ad plan for a slow month", json_mode=True, max_tokens=400)
    try:
        d = r.json()
    except Exception as e:
        _abstain("ads", "ad plan", Verdict(False, [f"model reply unusable: {e}"]))
        return None
    v = shape(d, {"headline": str, "text": str, "why_now": str})
    if v:
        allowed = {int(round(gap["gap"])), rules["per_day"], total, proj}
        said = " ".join([d["headline"], d["text"], d["why_now"]])
        public = f"{d['headline']} {d['text']}"
        amounts = dollar_amounts(said)
        if amounts - allowed:
            v.add(f"numbers that aren't Alex's: {sorted(amounts - allowed)}")
        if dollar_amounts(public):
            v.add("the ad strangers see shows money (Alex's gap, budget or prices); keep numbers in the note for Alex")
        if re.search(r"short(fall)?\b|\bgap\b|budget|cash|limited[- ‑]time|act now|today only|hurry|don'?t miss", public, re.I):
            v.add("the ad strangers see talks about Alex's money or pushes urgency")
        if not client and any(c.lower() in said.lower() for c in [p for p in pairs]):
            v.add("names a client who didn't agree to be named")
    if not v:
        _abstain("ads", "ad plan", v, d)
        return None
    req = approvals.propose(
        "ad_plan", {"places": rules["places"], "audience": rules["audience"], "per_day": rules["per_day"],
                    "days": rules["days"], "total": total, "headline": d["headline"], "text": d["text"],
                    "images": [pics["before"]["path"], pics["after"]["path"]]},
        summary=f"Boost a before/after post: ${rules['per_day']} a day for {rules['days']} days (${total})",
        why=d["why_now"],
        checks=[f"budget within your rule (${rules['per_day']}/day, {rules['days']} days)", "only when cash is short",
                "numbers only from your records", "client named only if your notes allow it"],
        reasoning=r.reasoning, model_label="Nemotron Super")
    if req:
        notify.ask(req)
    return req


@approvals.action("ad_plan", needs_approval=True)
def ad_plan(args: dict) -> str:
    """Kept doesn't run ads; a Yes saves the plan, ready to set up in the ad manager."""
    from .store import data_dir
    out = data_dir() / "outbox" / f"ad-plan-{now_iso().replace(':', '-')}.json"
    out.write_text(json.dumps(args, indent=1, ensure_ascii=False))
    return f"saved the ad plan to outbox/{out.name}; set it up in your ad manager"

