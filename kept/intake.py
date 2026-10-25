"""What kind of kitchen job is this, and what's the next step?

Alex works one way, and Kept follows it:
- a small repair (a handle, a hinge, a latch, a drawer, a door that won't close) is priced straight
  away at the hourly rate with the 2-hour minimum, from the photo if there is one; hardware is
  standard but matched to the style in the photo. No measuring visit.
- new fronts, a countertop, a backsplash or a whole new kitchen need real measurements, so Kept
  asks for rough ones and offers free measuring visits from Alex's calendar. A price is only ever
  "from" Alex's own list until the visit.
- when the client answers with one of the offered times, code books it.

Super reads the email (and what Nemotron VL saw in the photo) and names the job; code does the
prices, the times and the booking.
"""
from __future__ import annotations

import math
import re

from . import schedule
from .agent import _abstain, _msgs, note, read_notes_owner, sender
from .llm import router
from .store import read_notes
from .validators import Verdict, one_of, shape

JOBS = ["small_repair", "fronts", "countertop", "backsplash", "full_kitchen", "commercial", "question", "other"]
NEEDS_VISIT = {"fronts", "countertop", "backsplash", "full_kitchen", "commercial"}
SERVICE_LINE = {"fronts": "cabinet fronts", "countertop": "new countertop", "backsplash": "new backsplash",
                "full_kitchen": "full kitchen remodel", "commercial": "cafe counters"}


def _rate() -> int:
    m = re.search(r"hourly rate:\s*\$?\s*(\d+)", read_notes(), re.I)
    return int(m.group(1)) if m else 85


def _min_hours() -> int:
    m = re.search(r"(\d+)-hour minimum", read_notes(), re.I)
    return int(m.group(1)) if m else 2


def from_price(job: str) -> int | None:
    key = SERVICE_LINE.get(job)
    if not key:
        return None
    for line in read_notes().splitlines():
        if key in line.lower():
            m = re.search(r"from \$([\d,]+)", line)
            return int(m.group(1).replace(",", "")) if m else None
    return None


WORD_JOBS = [(re.compile(r"\b(hinge|handle|latch|knob|runner|drawer (fell|is loose|broke|won'?t)|door (hangs|fell|won'?t close))", re.I), "small_repair"),
             (re.compile(r"\bback ?splash", re.I), "backsplash"),
             (re.compile(r"\bcounter ?tops?\b|\bcounters?\b(?! ?(offer|argument))", re.I), "countertop"),
             (re.compile(r"\b(cabinet )?fronts\b|new (cabinet )?doors\b|refac", re.I), "fronts"),
             (re.compile(r"\b(new|whole|full|redo|remodel\w*) (a |the |our |my )?(kitchen|kich\w*|kitc\w*)\b|kitchen (remodel|renovation|update)", re.I), "full_kitchen")]
KITCHEN_WORDS = re.compile(
    r"kitchen|cabinet|counter|backsplash|splash|drawer|hinge|handle|door|tile|sink|faucet|remodel|renovat|repair|fix|"
    r"broken|loose|quote|estimate|visit|measur|price|cost|wood|shelf|shelves|pantry|island|install|replace|build|"
    r"kich|kitc|cabn|cabin|cuisine|cocina|"
    r"кухн|шкаф|столешниц|ремонт|фасад|cocina|gabinete|reparar", re.I)
WHERE_WORDS = re.compile(r"\b(\d{5}|street|st\.|ave|avenue|road|rd\.|blvd|lane|drive|way|place|neighbou?rhood|sellwood|alberta|"
                         r"pearl|hawthorne|st\.? johns|ladd|richmond|irvington|division|belmont|mississippi|nw|ne|se|sw|"
                         r"beaverton|gresham|tigard|lake oswego|milwaukie|vancouver)\b", re.I)
WHEN_WORDS = re.compile(r"\b(when|by|before|after|month|months|week|weeks|spring|summer|fall|autumn|winter|asap|soon|"
                        r"timeline|christmas|holiday|thanksgiving|january|february|march|april|may|june|july|august|"
                        r"september|october|november|december|next year|this year)\b", re.I)


def follow_up_questions(job: str, body: str, photo: bool, has_contract: bool, est_from_their_numbers: bool) -> list[str]:
    """What Alex would still want to know, at most two, and only what's really missing: never a form to fill in."""
    asks = []
    if job in NEEDS_VISIT and not has_contract and not est_from_their_numbers:
        asks.append("rough measurements if they have them: the length of each wall with cabinets and how many doors and drawers there are")
    if not photo and job in NEEDS_VISIT:
        asks.append("two or three photos of the kitchen from different angles (one of the whole room, one close up)")
    elif not photo and job == "small_repair":
        asks.append("a photo of the broken part, so Alex brings the right hardware")
    if (job in NEEDS_VISIT or job == "small_repair") and not has_contract and not WHERE_WORDS.search(body):
        asks.append("which part of Portland they're in (or the address), so Alex can plan the drive")
    if job in ("full_kitchen", "fronts", "commercial") and not WHEN_WORDS.search(body):
        asks.append("roughly when they'd like the work done")
    return asks[:2]


OTHER_TRADE = re.compile(r"\b(toilet|shower|bath ?tub|roof|gutter|chimney|paint(ing)?|electric(al|ian)?|wiring|breaker|outlet|"
                         r"hvac|furnace|heater|air ?con|plumb(ing|er)|sewer|lawn|fence|deck|driveway|window pane|siding)\b", re.I)
OUR_WORDS = re.compile(r"cabinet|vanit|counter|backsplash|drawer|hinge|shelf|shelves|pantry|island|kitchen", re.I)


def not_our_trade(subject: str, body: str) -> bool:
    """A job Alex doesn't do (a toilet, a roof, painting): no price, no visit, a kind 'not my trade'."""
    t = f"{subject} {body}"
    return bool(OTHER_TRADE.search(t)) and not OUR_WORDS.search(t)


def _known(addr: str, this_id: str) -> bool:
    """Someone Alex already deals with: they've written before, or they're in his promises, invoices or contracts.
    Their 'thanks!' or 'please send the Q3 receipts' is never off-topic (live, Oct 24: Alex's accountant asked
    for receipts and got 'I specialize in kitchens')."""
    from . import ledger, money
    from .reply import thread
    from .scope import contract_for
    a = addr.lower()
    return (any(t["id"] != this_id and t["dir"] in ("in", "out") for t in thread(addr))
            # rows read from this very email don't count: they were just written from the stranger's own words
            or any((r.get("contact") or "").lower() == a and r.get("source") != this_id for r in ledger.items())
            or any(i["contact"].lower() == a for i in money.load()["invoices"])
            or bool(contract_for(addr)))


def is_off_topic(job: str, subject: str, body: str, photo: bool) -> bool:
    """Not about anything Alex does: a 'question' or 'other' with no kitchen words and no photo."""
    return job in ("question", "other") and not photo and not KITCHEN_WORDS.search(f"{subject} {body}")


COMMERCIAL = re.compile(r"\b(cafe|café|coffee|restaurant|bakery|bar|clinic|dental|office|shop|store|boutique|salon|studio|gym)\b", re.I)


def assess(m: dict, photo: dict | None = None, has_contract: bool = False, web: dict | None = None,
           kind: str = "lead") -> dict:
    from . import estimate

    name, addr = sender(m)
    # a pick of an offered time is read and booked by code, whatever the model says about the job
    picked = schedule.match_pick(addr, m["body"])
    r = router.ask("plan", _msgs(
        f"{read_notes_owner()} runs {note('Business', 'a kitchen business')}. Read this email"
        + (" and what was seen in the photo they sent" if photo else "") + " and say what job it is:\n"
        "- small_repair: fix or replace a handle, hinge, latch, drawer, door or a small leak, keeping everything else\n"
        "- fronts: new cabinet doors and drawer fronts on the existing boxes\n"
        "- countertop / backsplash: replace just that\n"
        "- full_kitchen: take everything out and build a new kitchen\n"
        "- commercial: a cafe counter, shelving or a staff kitchenette\n"
        "- question / other: anything else\n"
        "For small_repair, estimate the hours on site (1 to 6). Copy any sizes THEY give (feet of wall with cabinets, "
        "number of doors and drawer fronts, countertop or backsplash square feet), and the materials they ask for. "
        "Say whether they push back on price (too expensive, can't afford it). Reply JSON: "
        '{"job": "...", "what": "one line", "repair_hours": 0, "sizes": {"cabinet_run_ft": null, "doors_and_drawers": null, '
        '"countertop_sqft": null, "backsplash_sqft": null}, "material": "", "price_objection": false}\n\n'
        + (f"PHOTO (Nemotron VL): {photo}\n\n" if photo else "")
        + f"From: {name}\nSubject: {m['subject']}\n\n{m['body'][:2500]}"),
        purpose=f"what job is {m['id']}", json_mode=True, max_tokens=400)
    try:
        d = r.json()
    except Exception as e:
        _abstain("intake", m["subject"], Verdict(False, [f"model reply unusable: {e}"]))
        d = {}
    job = str(d.get("job") or "").strip().lower()
    if job not in JOBS:
        # e.g. 'question/other': close enough to say we don't know the job, not to throw the email away
        job = "question" if "question" in job else "other" if job else "other"
    # the words are evidence too: "a new tile backsplash" is a backsplash job even if the model said "other"
    said = f"{m.get('subject', '')} {m['body']}"
    if job in ("question", "other"):
        for rx, j in WORD_JOBS:
            if rx.search(said):
                job = j
                break
    # the photo is evidence too: "what would you suggest?" next to a photo of a tired kitchen is a remodel enquiry
    if job in ("question", "other") and photo:
        job = {"full_kitchen": "full_kitchen", "refresh": "fronts", "small_repair": "small_repair"}.get(photo.get("scope"), job)
    # Tavily said who's writing: a verified cafe, clinic or shop is a commercial job, whatever the email calls it
    verified_biz = bool(web and web.get("facts")) and bool(COMMERCIAL.search(
        " ".join([web.get("kind", ""), web.get("business", "")] + [f["text"] for f in web.get("facts", [])])))
    if verified_biz and job in ("full_kitchen", "question", "other", "countertop", "fronts"):
        job = "commercial"
    # the words themselves count too: a model that misses "more than we can afford" mustn't lose the payment plan
    objection = bool(d.get("price_objection")) or bool(re.search(
        r"too (much|expensive|pricey)|can'?t afford|cannot afford|can'?t pay|more than we (expected|can)|over (our|my) budget|"
        r"дорого|не потянем|нет таких денег", m["body"], re.I))
    out = {"job": job, "what": d.get("what", "") or "", "price_objection": objection,
           "verified_business": verified_biz}
    # a stranger is anyone Alex doesn't already deal with (Kept's sorter may call small talk "personal")
    stranger = kind != "bill" and not has_contract and not _known(addr, m["id"])
    if not picked and stranger and not_our_trade(m.get("subject", ""), m["body"]):
        out["not_our_trade"] = True
        return out
    if is_off_topic(job, m.get("subject", ""), said, bool(photo)) and not picked and stranger:
        out["off_topic"] = True
        return out
    if picked:
        out["booked"] = schedule.book(picked, name, addr, out["what"] or picked.get("for", "measuring visit"))
        out["booked_label"] = picked["label"]
        return out
    if out["price_objection"]:
        last = estimate.last_for(addr)
        if last:
            out["estimate"] = last
            out["payment_plan"] = estimate.payment_plan(int(last["mid"]))
        return out
    if job == "small_repair" and has_contract:
        # Alex is already working at this kitchen under a signed agreement: the scope check decides what's
        # covered and prices any extra; a repair here is never priced as a separate call-out
        out["on_site"] = True
    elif job == "small_repair":
        hours = d.get("repair_hours") or 1
        hours = min(6, max(_min_hours(), math.ceil(float(hours)))) if isinstance(hours, (int, float)) else _min_hours()
        out.update(hours=hours, price=hours * _rate(), hardware_note=note("Hardware for repairs", ""))
        slots = schedule.free_slots(3)
        schedule.offer(addr, [{**s, "for": "repair visit"} for s in slots])
        out["slots"] = slots
    elif job in ("question", "other") and not has_contract and not out["price_objection"]:
        slots = schedule.free_slots(3)
        schedule.offer(addr, [{**s, "for": "visit"} for s in slots])
        out["slots"] = slots
    if job in NEEDS_VISIT:
        out["from_price"] = from_price(job)
        # only numbers that are really in their email count as theirs; the rest came from the photo
        body_nums = set(re.findall(r"\d+(?:\.\d+)?", m["body"]))
        their = {}
        for k, v in (d.get("sizes") or {}).items():
            n = estimate._num(v, add_up=(k == "doors_and_drawers"))
            if n and (str(v) in body_nums or f"{n:g}" in body_nums or str(int(n)) in body_nums):
                their[k] = n
        seen = {k: v for k, v in ((photo or {}).get("rough_sizes") or {}).items() if v}
        sizes = {**seen, **their}  # their own numbers win over the photo
        est = estimate.preliminary(job, sizes, d.get("material") or "")
        if est:
            est["sizes_from"] = "your numbers" if their else "your photo (rough)"
            out["estimate"] = est
            estimate.remember(addr, est, job)
        elif out["from_price"]:
            # no sizes yet: if they push back on price later, a payment plan can still be worked out on the
            # starting price from Alex's list
            fp = out["from_price"]
            estimate.remember(addr, {"low": fp, "high": fp, "mid": fp, "lines": [], "used": {},
                                     "sizes_from": "Alex's starting price"}, job)
        if has_contract:
            out["on_site"] = True  # Alex is already working at their kitchen and can measure there
        else:
            slots = schedule.free_slots(3)
            schedule.offer(addr, [{**s, "for": "measuring visit"} for s in slots])
            out["slots"] = slots
    out["ask"] = follow_up_questions(job, m["body"], bool(photo), has_contract,
                                     bool(out.get("estimate") and out["estimate"].get("sizes_from") == "your numbers"))
    return out


def _num_forms(n: int) -> str:
    """'4,500|4 500|4500' and the no-break space variants: how the number may appear in any language."""
    n = int(n)
    forms = {f"{n:,}", str(n), f"{n:,}".replace(",", " "), f"{n:,}".replace(",", "\u00a0"), f"{n:,}".replace(",", "\u202f")}
    return "|".join(sorted(forms))


def reply_rules(plan: dict) -> tuple[str, set[int], list[str]]:
    """(instructions for the reply, amounts it may name, words it must contain; 'a|b' means either)."""
    job = plan.get("job")
    allowed: set[int] = set()
    must: list[str] = []
    if plan.get("not_our_trade"):
        return ("They ask for work Alex doesn't do (Alex builds and fixes kitchens and cabinets only). Say so kindly in "
                "one or two sentences and suggest they look for the right tradesperson; don't name any company, give no "
                "price and no visit times. If it's urgent or about safety (water, electricity), say to call a "
                "specialist right away. Then one sentence on what Alex does do (kitchens, new cabinet fronts, counters, "
                "backsplashes, cabinet repairs) in case they ever need it.", allowed, must)
    if plan.get("off_topic"):
        return ("This message isn't about a kitchen job. Reply in two or three short, friendly sentences. Answer only "
                "what Alex's facts answer; don't give opinions or facts on unrelated topics and don't make anything up. "
                "Never promise to look something up, check or get back to them about an unrelated topic. "
                "If they ask whether they're talking to a bot: Alex's assistant Kept drafts replies and Alex reads and "
                "approves each one before it goes out. If they're rude, stay calm and polite. Then say in one sentence "
                "what Alex does (kitchens, new cabinet fronts, counters and backsplashes, small repairs, in Portland) "
                "and that a photo of their kitchen is the easiest way to start. No prices, no visit times.",
                allowed, must)
    asks = plan.get("ask") or []
    ask_line = (" Then, kindly and in one sentence, ask for " + " and ".join(asks) + ". Don't turn it into a list of questions."
                if asks else "")
    if plan.get("booked_label"):
        day = plan["booked_label"].split(",")[0]
        return (f"They picked a visit time: confirm it plainly ({plan['booked_label']}), and say what Alex will do "
                "then. A measuring visit is free.", allowed, [])
    if plan.get("price_objection"):
        pp = plan.get("payment_plan")
        if pp:
            allowed |= {pp["total"], pp["deposit"], pp["monthly"], plan["estimate"]["low"], plan["estimate"]["high"],
                        plan["estimate"]["mid"]}
            must.append(_num_forms(pp["monthly"]))
            return ("They say it's too much. Be kind and brief: say you understand, prices are up everywhere. Offer a "
                    f"personal payment plan written into the contract: {pp['pct']}% up front (${pp['deposit']:,}), then "
                    f"{pp['months']} equal monthly payments of ${pp['monthly']:,}, based on the estimate of about "
                    f"${pp['total']:,}. Also mention a cheaper path if it helps (new fronts and a countertop on the "
                    "existing cabinets instead of a whole new kitchen), without putting a number on it; Alex can price "
                    "it at the visit. Use no other dollar amounts than these.", allowed, must)
        return ("They say it's too much. Be kind; offer to look for a cheaper way (new fronts on the existing "
                "cabinets, or doing it in stages) at the visit. Don't name new numbers.", allowed, must)
    slots = plan.get("slots") or []
    slot_text = "; ".join(s["label"] for s in slots)
    if slots:
        must.append("SLOTS")  # any one of the offered times, in any language
    if job == "small_repair" and plan.get("on_site"):
        return ("Alex is already working at their kitchen under the agreement: say Alex will see to it while on "
                "site, and don't put a price on anything the agreement covers.", allowed, must)
    if job == "small_repair":
        allowed.add(plan["price"])
        must.append(_num_forms(plan["price"]))
        return (f"This is a small repair: no measuring visit is needed. Give the price now: ${plan['price']} "
                f"({plan['hours']} hours at the hourly rate), plus hardware, and say plainly that small jobs have a "
                "2-hour minimum because of the drive. Say the hardware will be standard parts matched as closely as "
                "possible to the style in their photo (or ask for a photo if they sent none). Since Alex is coming "
                "anyway: if the photo shows something else worth doing (tired fronts, an old backsplash, a worn "
                "counter), suggest ONE thing in a sentence, with its 'from' price from Alex's list, and offer to "
                f"measure for it on the same visit. Offer these times for the repair, exactly as written: {slot_text}." + ask_line,
                allowed, must)
    if job in NEEDS_VISIT:
        fp = plan.get("from_price")
        if fp:
            allowed.add(fp)
        est = plan.get("estimate")
        if est:
            allowed |= {est["low"], est["high"], est["mid"]} | {l["price"] for l in est["lines"]} | {l["total"] for l in est["lines"]}
            must.append(_num_forms(est["low"]) + "|" + _num_forms(est["mid"]))
            sizes = ", ".join(f"{v} {k.replace('_', ' ').replace('sqft', 'sq ft').replace('ft', 'ft')}" for k, v in est["used"].items())
            parts = "; ".join(f"{l['what']}: {l['qty']} {l['unit']} x ${l['price']:,}" if l["unit"] else f"{l['what']}: ${l['price']:,}"
                              for l in est["lines"])
            price_line = (f"Give a PRELIMINARY estimate of ${est['low']:,} to ${est['high']:,}, and show how it was worked "
                          f"out: sizes from {est['sizes_from']} ({sizes}); {parts}. Say clearly it's preliminary and the "
                          "exact price comes after the free measuring visit. Use no dollar amounts other than these. ")
        elif fp:
            price_line = f"You may say this kind of job starts from ${fp:,}; the real price comes after the visit. "
        else:
            price_line = "Don't give any price before the visit. "
        if plan.get("on_site"):
            return ("Alex is already working at their kitchen, so offer to measure there this week. " + price_line + ask_line,
                    allowed, must)
        return (price_line + f"Offer a free measuring visit at one of these times, exactly as written: {slot_text}. "
                "If their photo shows a way to make the kitchen nicer or easier to use (more storage, a glass or "
                "marble-look backsplash, brighter fronts), mention one idea in a sentence." + ask_line, allowed, must)
    if slots:
        return ("If a visit would help, offer one of these free times, exactly as written: " + slot_text + ".",
                allowed, [])
    return ("", allowed, must)
