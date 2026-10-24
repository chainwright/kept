"""Propose, verify, or abstain.

The model proposes; plain code decides whether the proposal is fit to use.
Nothing here asks a model for its opinion of itself. If a check fails, Kept
does not act. It records the reason and tells the owner what it could not verify.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta
from typing import Any, Iterable


@dataclass
class Verdict:
    ok: bool
    problems: list[str] = field(default_factory=list)

    def __bool__(self) -> bool:
        return self.ok

    def add(self, problem: str) -> None:
        self.ok = False
        self.problems.append(problem)

    def merge(self, other: "Verdict") -> "Verdict":
        for p in other.problems:
            self.add(p)
        return self


def shape(obj: Any, required: dict[str, type]) -> Verdict:
    """Required keys are present and have the expected type."""
    v = Verdict(True)
    if not isinstance(obj, dict):
        v.add(f"expected an object, got {type(obj).__name__}")
        return v
    for key, typ in required.items():
        if key not in obj:
            v.add(f"missing field '{key}'")
        elif not isinstance(obj[key], typ):
            v.add(f"field '{key}' should be {typ.__name__}, got {type(obj[key]).__name__}")
    return v


def _norm(s: str) -> str:
    return re.sub(r"\s+", " ", re.sub(r"[“”\"'’‘]", "", s)).strip().lower()


def grounded(claims: Iterable[dict], sources: dict[str, str]) -> Verdict:
    """Every claim must point at a source we actually fetched, and quote it.

    claims:  [{"text": ..., "source": "<source id>", "quote": "<exact words from it>"}]
    sources: {"<source id>": "<full text we fetched>"}
    The quote has to appear in the source text (whitespace and quote marks aside).
    That one rule kills most invented facts: a model can't quote a page it never saw.
    """
    v = Verdict(True)
    for i, c in enumerate(claims):
        # models write "[web:1a2b]" when the listing showed the id in brackets; same source
        sid, quote = str(c.get("source", "")).strip().strip("[]").strip(), str(c.get("quote", ""))
        if sid not in sources and f"web:{sid}" in sources:  # the model dropped the prefix
            sid = f"web:{sid}"
        if sid not in sources and sid.lower() in sources:  # "[LEDGER:7CEC0B5C]"
            sid = sid.lower()
        if sid not in sources:
            v.add(f"claim {i + 1} cites '{sid}', which Kept never fetched")
            continue
        if len(_norm(quote)) < 12:
            v.add(f"claim {i + 1} has no usable quote from its source")
            continue
        # a quote may skip words with "..." (two places on one page); then every piece must be on the page
        page = _norm(sources[sid])
        pieces = [p for p in (_norm(x) for x in re.split(r"\.\.\.|…", quote)) if len(p) >= 8]
        if not pieces or any(p not in page for p in pieces):
            v.add(f"claim {i + 1}: the quoted words are not in source '{sid}'")
    return v


_PLACEHOLDER = re.compile(r"\[(?:name|company|date|your name|insert[^\]]*)\]|\{\{.*?\}\}|lorem ipsum|TODO", re.I)


def sendable_text(text: str, *, max_chars: int = 1500, must_mention: Iterable[str] = ()) -> Verdict:
    """A message a human will receive: no template holes, sane length, right person."""
    v = Verdict(True)
    t = text.strip()
    if not t:
        v.add("the draft is empty")
        return v
    if len(t) > max_chars:
        v.add(f"the draft is {len(t)} characters; the limit is {max_chars}")
    m = _PLACEHOLDER.search(t)
    if m:
        v.add(f"the draft still has a template hole: '{m.group(0)}'")
    for word in must_mention:
        if word and word.lower() not in t.lower():
            v.add(f"the draft never mentions '{word}'")
    return v


def plausible_due(value: str | None, *, today: date | None = None, horizon_days: int = 400) -> Verdict:
    """A due date the model extracted must parse and be within a sane window."""
    v = Verdict(True)
    if value in (None, "", "none"):
        return v
    today = today or date.today()
    try:
        d = datetime.fromisoformat(str(value)[:10]).date()
    except ValueError:
        v.add(f"due date '{value}' is not a date")
        return v
    if d < today - timedelta(days=60):
        v.add(f"due date {d} is long past; probably misread")
    if d > today + timedelta(days=horizon_days):
        v.add(f"due date {d} is more than {horizon_days} days away; probably misread")
    return v


def one_of(value: Any, allowed: Iterable[str], field_name: str) -> Verdict:
    v = Verdict(True)
    allowed = list(allowed)
    if value not in allowed:
        v.add(f"{field_name} '{value}' is not one of {allowed}")
    return v


_MONTHS = {m: i for i, m in enumerate(["jan", "feb", "mar", "apr", "may", "jun", "jul", "aug", "sep", "oct",
                                       "nov", "dec"], start=1)}


def dates_in(text: str, today: date) -> list[date]:
    found = []
    for y, m, d in re.findall(r"\b(20\d\d)-(\d\d)-(\d\d)\b", text):
        try:
            found.append(date(int(y), int(m), int(d)))
        except ValueError:
            pass
    for mon, d in re.findall(r"\b(jan|feb|mar|apr|may|jun|jul|aug|sep|oct|nov|dec)[a-z]*\.? (\d{1,2})\b", text, re.I):
        try:
            found.append(date(today.year, _MONTHS[mon.lower()[:3]], int(d)))
        except ValueError:
            pass
    return found


def honest_email(text: str, *, recipient_first: str, owner_first: str, today: date | None = None,
                 allowed_dates: set | None = None) -> Verdict:
    """Catches the mistakes we saw in live runs: greeting the owner instead of the client,
    and promising a date that has already passed."""
    today = today or date.today()
    v = Verdict(True)
    first_line = text.strip().splitlines()[0] if text.strip() else ""
    # the greeting is the opening clause ("Hi Maria,"), not a one-line email's sign-off ("Thanks, Alex")
    greeting = re.split(r"[,!:\u2014\-]", first_line, maxsplit=1)[0][:40]
    if owner_first and re.search(rf"\b{re.escape(owner_first)}\b", greeting, re.I) and \
            owner_first.lower() != recipient_first.lower():
        v.add(f"the greeting addresses {owner_first}, the sender, instead of {recipient_first}")
    if recipient_first and recipient_first.lower() not in text.lower():
        v.add(f"the draft never mentions '{recipient_first}'")
    past = [d for d in dates_in(text, today) if d < today and d not in (allowed_dates or set())]
    if past:
        v.add(f"the draft mentions {past[0].isoformat()}, which has already passed")
    return v


_WEEKDAYS = ["monday", "tuesday", "wednesday", "thursday", "friday", "saturday", "sunday"]


def resolve_when(words: str, today: date) -> date | None:
    """Turn 'by Friday', 'tomorrow', 'end of the week', 'next week', 'Oct 30' into a date.
    Models are unreliable at calendar arithmetic (live run: 'Friday' -> a Tuesday), so code does it."""
    w = (words or "").lower()
    if not w.strip():
        return None
    if "today" in w or "tonight" in w or "end of day" in w or "eod" in w:
        return today
    if "tomorrow" in w:
        return today + timedelta(days=1)
    nxt = "next week" in w or ("next" in w and any(d in w for d in _WEEKDAYS))
    for i, name in enumerate(_WEEKDAYS):
        if re.search(rf"\b{name}\b", w):
            ahead = (i - today.weekday()) % 7 or 7
            d = today + timedelta(days=ahead)
            if "next" in w and ahead < 7 and today.weekday() < i:
                d += timedelta(days=7)  # "next Friday" said on a Tuesday means the Friday after this one
            return d
    if "end of the week" in w or "end of week" in w or "this week" in w:
        return today + timedelta(days=(4 - today.weekday()) % 7)
    if nxt:  # "next week": the Friday of next week, the latest day it can still mean
        return today + timedelta(days=(7 - today.weekday())) + timedelta(days=4)
    hits = dates_in(w, today)
    if hits:
        d = hits[0]
        return d if d >= today - timedelta(days=60) else d.replace(year=d.year + 1)
    return None


_NUM = r"\d{1,3}(?:[ ,\u00a0\u202f]\d{3})+(?:\.\d\d)?|\d+(?:\.\d\d)?"
_DOLLARS = re.compile(rf"\$\s?({_NUM})|({_NUM})\s?(?:\$|USD\b|dollars?\b|долл)", re.I)


def dollar_amounts(text: str) -> set[int]:
    """Every dollar figure in a text, written the way people write them in any language:
    "$4,500", "$4 500", "4 500 $", "4500 USD". Used to make sure a draft names no price
    that didn't come from the owner's records."""
    out = set()
    for a, b in _DOLLARS.findall(text or ""):
        raw = re.sub(r"[ ,\u00a0\u202f]", "", a or b)
        try:
            out.add(int(round(float(raw))))
        except ValueError:
            pass
    return out
