"""Well-timed offers: a reason, the right person, inside your rules, or nothing at all.

A discount at the wrong moment teaches clients to wait for one and eats the margin.
So the default is no offer. One is only proposed when all of these line up:

  1. an occasion, from a calendar code computes (holidays, and seasons that matter to
     this client's kind of business: a bakery's December, a dental office's year-end
     insurance rush, a gym or studio's January);
  2. the right person: a past client who pays on time and hasn't ordered in a while,
     or a lead who went quiet after a quote. Anyone with an overdue invoice is skipped;
  3. the owner's own rules from notes.md: maximum discount, minimum price, how often;
  4. Nemotron Ultra judging the offer worth making at all, preferring a package or
     priority slot over a price cut.

Code checks the numbers in the email match what was approved. Every offer waits for Yes.
"""
from __future__ import annotations

import json
import re
from datetime import date, datetime, timedelta

from . import approvals, ledger, money
from .agent import _abstain, _msgs, read_notes_owner
from .llm import router
from .store import journal, now_iso, read_json, read_notes, write_json
from .tools import notify
from .validators import Verdict, honest_email, sendable_text, shape

FILE = "offers.json"
INDUSTRY_WORDS = {
    "bakery": r"bak|cafe|coffee|patisser|pastry", "dental": r"dental|dentist|clinic|ortho",
    "fitness": r"yoga|gym|fitness|pilates|studio", "retail": r"shop|store|boutique",
}


def _nth_weekday(year: int, month: int, weekday: int, n: int) -> date:
    d = date(year, month, 1)
    d += timedelta(days=(weekday - d.weekday()) % 7)
    return d + timedelta(weeks=n - 1)


def calendar(today: date) -> list[dict]:
    """Occasions in the next ~100 days. 'for' lists the kinds of business it suits; 'all' suits everyone."""
    y = today.year
    out = []
    for yr in (y, y + 1):
        thanksgiving = _nth_weekday(yr, 11, 3, 4)
        out += [
            {"id": f"black-friday-{yr}", "name": "Black Friday / Small Business Saturday", "date": thanksgiving + timedelta(days=1), "for": ["retail", "bakery"]},
            {"id": f"holiday-season-{yr}", "name": "holiday season", "date": date(yr, 12, 1), "for": ["bakery", "retail"]},
            {"id": f"year-end-benefits-{yr}", "name": "year-end insurance benefits rush", "date": date(yr, 11, 15), "for": ["dental"]},
            {"id": f"new-year-{yr + 1}", "name": "New Year resolutions", "date": date(yr + 1, 1, 2), "for": ["fitness"]},
            {"id": f"valentines-{yr}", "name": "Valentine's Day", "date": date(yr, 2, 14), "for": ["bakery", "retail"]},
            {"id": f"new-year-planning-{yr + 1}", "name": "new-year website refresh", "date": date(yr + 1, 1, 12), "for": ["all"]},
        ]
    return sorted([o for o in out if 10 <= (o["date"] - today).days <= 100], key=lambda o: o["date"])


def rules() -> dict:
    n = read_notes()
    pct = re.search(r"max(?:imum)? discount[^\d]*(\d+)\s*%", n, re.I)
    floor = re.search(r"minimum (?:project )?price[^\d]*\$?\s*([\d,]+)", n, re.I)
    every = re.search(r"one offer per client per (\d+) days", n, re.I)
    return {"max_discount": int(pct.group(1)) if pct else 0,
            "min_price": int(floor.group(1).replace(",", "")) if floor else 0,
            "every_days": int(every.group(1)) if every else 60}


def industry(text: str) -> str:
    t = text.lower()
    return next((k for k, pat in INDUSTRY_WORDS.items() if re.search(pat, t)), "other")


def candidates(today: date) -> tuple[list[dict], list[dict]]:
    """(eligible, skipped-with-reason). Plain rules, no model."""
    book, r = money.load(), rules()
    sent = read_json(FILE, [])
    inbox = read_json("inbox.json", [])
    eligible, skipped = [], []
    by_client: dict[str, list[dict]] = {}
    for inv in book["invoices"]:
        by_client.setdefault(inv["client"], []).append(inv)
    for client, invs in by_client.items():
        contact = invs[-1]["contact"]
        overdue = [i for i in invs if not i.get("paid_on") and datetime.fromisoformat(i["due"]).date() < today]
        open_work = [i for i in invs if not i.get("paid_on")]
        last = max(datetime.fromisoformat(i["issued"]).date() for i in invs)
        recent = [o for o in sent if o["client"] == client and
                  (today - datetime.fromisoformat(o["ts"][:10]).date()).days < r["every_days"]]
        owed = [x for x in ledger.open_sorted(today, which="i_owe") if (x.get("contact") or "").lower() == contact.lower()]
        wrote = [m for m in inbox if contact.lower() in m.get("from", "").lower()
                 and (today - datetime.fromisoformat(m["date"][:10]).date()).days <= 7]
        why_not = ("owes an overdue invoice" if overdue else
                   "you still owe them work" if owed else
                   "has a project in progress" if open_work else
                   "wrote to you this week; answer them before pitching anything" if wrote else
                   f"got an offer in the last {r['every_days']} days" if recent else
                   "ordered recently" if (today - last).days < 45 else None)
        info = {"client": client, "contact": contact, "kind": "past client", "industry": industry(contact + " " + client),
                "last_order_days": (today - last).days, "habit": money.payment_habit(client, book)}
        (skipped if why_not else eligible).append({**info, "why_not": why_not} if why_not else info)
    return eligible, skipped


def propose(today: date | None = None) -> dict:
    today = today or date.today()
    r = rules()
    if not r["max_discount"] or not r["min_price"]:
        return {"offers": [], "note": "Set 'Max discount' and 'Minimum project price' in notes.md first."}
    eligible, skipped = candidates(today)
    occasions = calendar(today)
    pairs = []
    for c in eligible:
        fits = [o for o in occasions if c["industry"] in o["for"] or "all" in o["for"]]
        if fits:
            pairs.append({**c, "occasions": [{"id": o["id"], "name": o["name"], "date": o["date"].isoformat()} for o in fits[:2]]})
    result = {"ts": now_iso(), "skipped": skipped, "offers": [], "considered": [p["client"] for p in pairs]}
    if not pairs:
        write_json("offers_plan.json", result)
        return result
    cash = money.forecast(30, today)
    resp = router.ask("judge", _msgs(
        f"{read_notes_owner()} runs a one-person web studio (hourly rate in notes). For each past client below, "
        "decide whether a seasonal offer is worth making now, or not at all. Prefer a package or a priority slot "
        f"over a price cut; a discount may not exceed {r['max_discount']}% and the price may not go below "
        f"${r['min_price']}. Only offer what helps the client's own season. Cash is "
        f"{'short soon' if cash['short'] else 'fine'}, which makes a sale more useful but is never a reason to "
        "discount deeper. Reply JSON: "
        '{"offers": [{"client": "...", "make_offer": true|false, "occasion_id": "...", "what": "package or work offered", '
        '"price": 0, "discount_pct": 0, "book_by": "YYYY-MM-DD", "why": "one line"}]}\n\n'
        + json.dumps(pairs, ensure_ascii=False)), purpose="seasonal offers", json_mode=True, max_tokens=1200)
    try:
        decisions = resp.json().get("offers") or []
    except Exception as e:
        _abstain("offers", "seasonal offers", Verdict(False, [f"model reply unusable: {e}"]))
        return result
    by_client = {p["client"]: p for p in pairs}
    for d in decisions:
        if not isinstance(d, dict) or not d.get("make_offer"):
            if isinstance(d, dict):
                result.setdefault("declined", []).append({"client": d.get("client"), "why": d.get("why")})
            continue
        p = by_client.get(d.get("client"))
        v = shape(d, {"what": str, "why": str})
        occ = next((o for o in (p or {}).get("occasions", []) if o["id"] == d.get("occasion_id")), None)
        if not p:
            v.add(f"'{d.get('client')}' wasn't one of the eligible clients")
        if p and not occ:
            v.add(f"occasion '{d.get('occasion_id')}' isn't on the calendar for this client")
        price, pct = d.get("price"), d.get("discount_pct") or 0
        if not isinstance(price, (int, float)) or price < r["min_price"]:
            v.add(f"price {price} is below your minimum ${r['min_price']}")
        if not isinstance(pct, (int, float)) or pct < 0 or pct > r["max_discount"]:
            v.add(f"discount {pct}% is outside your limit of {r['max_discount']}%")
        try:
            book_by = datetime.fromisoformat(str(d.get("book_by"))[:10]).date()
            if occ and not (today < book_by <= datetime.fromisoformat(occ["date"]).date()):
                v.add(f"book-by date {book_by} isn't between today and the occasion")
        except ValueError:
            v.add(f"book-by date '{d.get('book_by')}' isn't a date")
        if not v:
            _abstain("offers", str(d.get("client")), v, d)
            continue
        req = _draft(p, d, occ, resp.reasoning)
        if req:
            result["offers"].append(req["id"])
    write_json("offers_plan.json", result)
    journal(f"Seasonal offers: considered {len(pairs)}, proposed {len(result['offers'])}, skipped {len(skipped)}")
    return result


def _draft(p: dict, d: dict, occ: dict, reasoning: str) -> dict | None:
    first = p["client"].split(" ")[0]
    pct = int(d.get("discount_pct") or 0)
    price = int(d["price"])
    book_by = datetime.fromisoformat(d["book_by"][:10]).date()
    r = router.ask("draft", _msgs(
        f"Write a short, warm email FROM {read_notes_owner()} TO {p['client']}, a past client, ahead of "
        f"{occ['name']}. Offer: {d['what']} for ${price}" + (f" ({pct}% off)" if pct else "") +
        f", if booked by {book_by:%B %-d}. Tie it to their business, not to a sale. No pressure, no "
        "'limited time' language. State the price once as a plain number. Greet "
        f"{first}, sign as {read_notes_owner()}. Under 110 words. "
        'Reply JSON: {"subject": "...", "body": "..."}', "follow_up"),
        purpose=f"offer for {p['client']}", json_mode=True, max_tokens=500)
    try:
        e = r.json()
    except Exception as ex:
        _abstain("offers", p["client"], Verdict(False, [f"model reply unusable: {ex}"]))
        return None
    v = shape(e, {"subject": str, "body": str})
    if v:
        body = e["body"]
        v.merge(sendable_text(body, max_chars=900))
        v.merge(honest_email(body, recipient_first=first, owner_first=read_notes_owner().split(" ")[0]))
        amounts = {int(float(x.replace(",", ""))) for x in re.findall(r"\$([\d,]+(?:\.\d\d)?)", body)}
        if price not in amounts:
            v.add(f"the email doesn't state the approved price ${price}")
        if amounts - {price}:
            v.add(f"the email mentions prices that weren't approved: {sorted(amounts - {price})}")
        pcts = {int(x) for x in re.findall(r"(\d+)\s*%", body)}
        if pcts - ({pct} if pct else set()):
            v.add(f"the email mentions a discount that wasn't approved: {sorted(pcts)}")
        if re.search(r"\b(limited time|act now|hurry|last chance|only today)\b", body, re.I):
            v.add("pressure language")
    if not v:
        _abstain("offers", p["client"], v, e)
        return None
    req = approvals.propose(
        "send_email", {"to": p["contact"], "subject": e["subject"], "body": e["body"], "offer_client": p["client"]},
        summary=f"Offer {p['client']}: {d['what']} for ${price}" + (f" ({pct}% off)" if pct else ""),
        why=f"{occ['name']} on {occ['date']}; {d['why']}",
        checks=[f"discount within your {rules()['max_discount']}% limit", f"price above your ${rules()['min_price']} minimum",
                "no other prices or discounts in the email", "no pressure language", "pays on time, no overdue invoices"],
        reasoning=reasoning, model_label="Nemotron Ultra")
    if req:
        sent = read_json(FILE, [])
        sent.append({"client": p["client"], "ts": now_iso(), "approval": req["id"], "occasion": occ["id"]})
        write_json(FILE, sent)
        notify.ask(req)
    return req
