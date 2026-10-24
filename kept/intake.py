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


def assess(m: dict, photo: dict | None = None, has_contract: bool = False) -> dict:
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
    # the photo is evidence too: "what would you suggest?" next to a photo of a tired kitchen is a remodel enquiry
    if job in ("question", "other") and photo:
        job = {"full_kitchen": "full_kitchen", "refresh": "fronts", "small_repair": "small_repair"}.get(photo.get("scope"), job)
    out = {"job": job, "what": d.get("what", "") or "", "price_objection": bool(d.get("price_objection"))}
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
    if job == "small_repair":
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
        their = {k: v for k, v in (d.get("sizes") or {}).items()
                 if v and (str(v) in body_nums or str(int(float(v))) in body_nums)}
        seen = {k: v for k, v in ((photo or {}).get("rough_sizes") or {}).items() if v}
        sizes = {**seen, **their}  # their own numbers win over the photo
        est = estimate.preliminary(job, sizes, d.get("material") or "")
        if est:
            est["sizes_from"] = "your numbers" if their else "your photo (rough)"
            out["estimate"] = est
            estimate.remember(addr, est, job)
        if has_contract:
            out["on_site"] = True  # Alex is already working at their kitchen and can measure there
        else:
            slots = schedule.free_slots(3)
            schedule.offer(addr, [{**s, "for": "measuring visit"} for s in slots])
            out["slots"] = slots
    return out


def reply_rules(plan: dict) -> tuple[str, set[int], list[str]]:
    """(instructions for the reply, amounts it may name, words it must contain; 'a|b' means either)."""
    job = plan.get("job")
    allowed: set[int] = set()
    must: list[str] = []
    if plan.get("booked_label"):
        day = plan["booked_label"].split(",")[0]
        return (f"They picked a visit time: confirm it plainly ({plan['booked_label']}), and say what Alex will do "
                "then. A measuring visit is free.", allowed, [day])
    if plan.get("price_objection"):
        pp = plan.get("payment_plan")
        if pp:
            allowed |= {pp["total"], pp["deposit"], pp["monthly"], plan["estimate"]["low"], plan["estimate"]["high"],
                        plan["estimate"]["mid"]}
            must.append(f"${pp['monthly']:,}|${pp['monthly']}")
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
        must.append("|".join(s["label"].split(",")[0] for s in slots))  # any one of the offered days
    if job == "small_repair":
        allowed.add(plan["price"])
        must.append(f"${plan['price']}")
        return (f"This is a small repair: no measuring visit is needed. Give the price now: ${plan['price']} "
                f"({plan['hours']} hours at the hourly rate), plus hardware, and say plainly that small jobs have a "
                "2-hour minimum because of the drive. Say the hardware will be standard parts matched as closely as "
                "possible to the style in their photo (or ask for a photo if they sent none). Since Alex is coming "
                "anyway: if the photo shows something else worth doing (tired fronts, an old backsplash, a worn "
                "counter), suggest ONE thing in a sentence, with its 'from' price from Alex's list, and offer to "
                f"measure for it on the same visit. Offer these times for the repair, exactly as written: {slot_text}.",
                allowed, must)
    if job in NEEDS_VISIT:
        fp = plan.get("from_price")
        if fp:
            allowed.add(fp)
        est = plan.get("estimate")
        if est:
            allowed |= {est["low"], est["high"], est["mid"]} | {l["price"] for l in est["lines"]} | {l["total"] for l in est["lines"]}
            must.append(f"${est['low']:,}|${est['low']}|${est['mid']:,}|${est['mid']}")
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
            return ("Alex is already working at their kitchen, so offer to measure there this week. " + price_line,
                    allowed, must)
        ask = "" if est and est["sizes_from"] == "your numbers" else (
            "Ask for rough measurements if they can: the length of each wall with cabinets and how many doors and "
            "drawers there are. ")
        return (price_line + ask + f"Offer a free measuring visit at one of these times, exactly as written: {slot_text}. "
                "If their photo shows a way to make the kitchen nicer or easier to use (more storage, a glass or "
                "marble-look backsplash, brighter fronts), mention one idea in a sentence.", allowed, must)
    if slots:
        return ("If a visit would help, offer one of these free times, exactly as written: " + slot_text + ".",
                allowed, [])
    return ("", allowed, must)
