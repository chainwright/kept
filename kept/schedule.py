"""Alex's week: job-site days and measuring visits.

Visit times come from the owner's notes ("weekdays at 16:30 and 17:30, Saturdays at 10:00..."),
busy days from the calendar file. Code picks the free slots; a model never invents a time. When a
client answers with one of the slots they were offered, code matches it and books it.
"""
from __future__ import annotations

import re
import uuid
from datetime import date, datetime, timedelta

from .store import journal, locked, now_iso, read_json, read_notes, write_json

FILE = "calendar.json"
WEEKDAYS = ["monday", "tuesday", "wednesday", "thursday", "friday", "saturday", "sunday"]


def load() -> dict:
    return read_json(FILE, {"events": [], "offered": {}})


def visit_times() -> dict[str, list[str]]:
    """{'weekday': ['16:30', '17:30'], 'saturday': [...]} from notes.md."""
    line = next((l for l in read_notes().splitlines() if l.lower().lstrip("- ").startswith("measuring visits:")), "")
    out = {"weekday": [], "saturday": [], "sunday": []}
    for part in re.split(r",\s*(?=[A-Z][a-z]+days?\b)|;", line.split(":", 1)[-1]):
        times = re.findall(r"\b(\d{1,2}:\d{2})\b", part)
        p = part.lower()
        if "weekday" in p:
            out["weekday"] += times
        elif "saturday" in p:
            out["saturday"] += times
        elif "sunday" in p and "never" not in p:
            out["sunday"] += times
    return out


def clock(hhmm: str) -> str:
    hh, mm = (int(x) for x in hhmm.split(":"))
    return f"{hh - 12 if hh > 12 else hh}:{mm:02d} {'pm' if hh >= 12 else 'am'}"


def _busy(day: date) -> list[dict]:
    return [e for e in load()["events"] if e["date"] == day.isoformat()]


def free_slots(n: int = 3, start: date | None = None, horizon: int = 10) -> list[dict]:
    """The next n free visit slots, at most one a day so the client gets a real choice."""
    start = start or date.today() + timedelta(days=1)
    rules = visit_times()
    out = []
    for i in range(horizon):
        d = start + timedelta(days=i)
        times = rules["saturday"] if d.weekday() == 5 else rules["sunday"] if d.weekday() == 6 else rules["weekday"]
        taken = {e["time"] for e in _busy(d) if e.get("time")}
        if any(e.get("all_day_visits_off") for e in _busy(d)):
            continue
        free = [t for t in times if t not in taken]
        if free:
            out.append({"date": d.isoformat(), "time": free[0], "label": f"{d:%A}, {d:%b} {d.day} at {clock(free[0])}"})
        if len(out) >= n:
            break
    return out


def offer(addr: str, slots: list[dict]) -> None:
    with locked():
        cal = load()
        cal.setdefault("offered", {})[addr.lower()] = slots
        write_json(FILE, cal)


def match_pick(addr: str, text: str) -> dict | None:
    """Which offered slot did they pick? Code reads the weekday and the time; anything vaguer stays unbooked."""
    offered = load().get("offered", {}).get(addr.lower()) or []
    t = text.lower()
    hits = []
    for s in offered:
        d = datetime.fromisoformat(s["date"]).date()
        day_named = WEEKDAYS[d.weekday()] in t or f"{d:%b} {d.day}".lower() in t or f"{d:%B} {d.day}".lower() in t
        if day_named:
            hits.append((_time_named(t, s["time"]), s))
    if not hits:
        return None
    hits.sort(key=lambda x: not x[0])
    return hits[0][1] if (hits[0][0] or len(hits) == 1) else None


def _time_named(t: str, hhmm: str) -> bool:
    hh, mm = (int(x) for x in hhmm.split(":"))
    h12 = hh - 12 if hh > 12 else hh
    suffix = "pm" if hh >= 12 else "am"
    if hhmm in t or f"{h12}:{mm:02d}" in t:
        return True
    return mm == 0 and bool(re.search(rf"\b{h12}\s*{suffix}\b", t))


def book(slot: dict, who: str, addr: str, what: str) -> dict:
    with locked():
        cal = load()
        ev = {"id": uuid.uuid4().hex[:8], "date": slot["date"], "time": slot["time"], "kind": "visit",
              "who": who, "contact": addr.lower(), "what": what, "booked": now_iso()}
        cal["events"].append(ev)
        cal.get("offered", {}).pop(addr.lower(), None)
        write_json(FILE, cal)
    journal(f"Booked a measuring visit: {who}, {slot['label']} ({what})")
    from . import ledger
    ledger.add(f"Measuring visit at {who.split(' ')[0]}'s kitchen, {slot['time']}", who=who, contact=addr,
               due=slot["date"], origin="calendar", direction="i_owe", quote=slot["label"])
    return ev


def upcoming(days: int = 14) -> list[dict]:
    today = date.today().isoformat()
    end = (date.today() + timedelta(days=days)).isoformat()
    return sorted([e for e in load()["events"] if today <= e["date"] <= end], key=lambda e: (e["date"], e.get("time", "")))
