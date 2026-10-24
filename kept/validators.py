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
        sid, quote = str(c.get("source", "")), str(c.get("quote", ""))
        if sid not in sources:
            v.add(f"claim {i + 1} cites '{sid}', which Kept never fetched")
            continue
        if len(_norm(quote)) < 12:
            v.add(f"claim {i + 1} has no usable quote from its source")
            continue
        if _norm(quote) not in _norm(sources[sid]):
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
