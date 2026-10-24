"""How reliable are your promises, really?

Kept looks at every promise you've closed: when it was due, when it was actually done.
From that it knows, for example, that your "I'll send the quote by Friday" usually lands
two days late. When you're about to make the same kind of promise again, it suggests the
date you'll actually hit. Plain arithmetic over your own ledger, no model involved.
"""
from __future__ import annotations

import re
import statistics
from dataclasses import dataclass
from datetime import date, datetime, timedelta

from . import ledger

# kinds of work, recognised from the promise text by keyword
KINDS = {
    "quote": r"\b(quote|estimate|proposal|rates?|pricing)\b",
    "fix": r"\b(fix|bug|broken|repair|debug)\b",
    "design": r"\b(design|mockup|logo|layout|photos?|banner)\b",
    "send": r"\b(send|share|deliver|upload)\b",
    "reply": r"\b(reply|answer|get back|confirm|call)\b",
    "pay": r"\b(pay|invoice|bill|renew)\b",
}
MIN_HISTORY = 3  # fewer closed promises than this and we don't pretend to know


def kind_of(text: str) -> str:
    t = text.lower()
    for k, pat in KINDS.items():
        if re.search(pat, t):
            return k
    return "other"


def _d(s: str | None) -> date | None:
    if not s:
        return None
    try:
        return datetime.fromisoformat(s[:10]).date()
    except ValueError:
        return None


def slip_days(row: dict) -> int | None:
    """Days late (positive) or early (negative) for a promise closed as done."""
    due, closed = _d(row.get("due")), _d(row.get("closed"))
    if row.get("status") != "done" or not due or not closed:
        return None
    return (closed - due).days


@dataclass
class Record:
    kept: int          # done on or before the due date
    total: int         # done with a due date
    median_slip: float  # days; 0 means on time
    late_slips: list[int]

    @property
    def rate(self) -> float:
        return self.kept / self.total if self.total else 0.0


def _record(rows: list[dict]) -> Record:
    slips = [s for s in (slip_days(r) for r in rows) if s is not None]
    if not slips:
        return Record(0, 0, 0.0, [])
    return Record(sum(1 for s in slips if s <= 0), len(slips), float(statistics.median(slips)),
                  [s for s in slips if s > 0])


def report() -> dict:
    """Overall, per kind of work, per person, and per weekday the promise was due."""
    done = [r for r in ledger.items() if slip_days(r) is not None]
    by = lambda key: {k: _record([r for r in done if key(r) == k]) for k in {key(r) for r in done}}
    out = {"overall": _record(done),
           "by_kind": by(lambda r: kind_of(r["text"])),
           "by_person": by(lambda r: r.get("who") or "?"),
           "by_weekday": by(lambda r: _d(r["due"]).strftime("%A"))}
    return out


def realistic_due(text: str, promised: str | date, who: str = "") -> dict | None:
    """If history says this kind of promise usually slips, return the date you'd actually hit."""
    promised_d = _d(promised) if isinstance(promised, str) else promised
    if not promised_d:
        return None
    rep = report()
    k = kind_of(text)
    rec = rep["by_kind"].get(k)
    basis = f"'{k}' promises"
    if not rec or rec.total < MIN_HISTORY:
        rec, basis = rep["overall"], "all your promises"
    if rec.total < MIN_HISTORY or rec.median_slip <= 0:
        return None
    shift = int(round(rec.median_slip))
    suggested = promised_d + timedelta(days=shift)
    while suggested.weekday() >= 5:  # land on a working day
        suggested += timedelta(days=1)
    return {
        "kind": k, "promised": promised_d.isoformat(), "suggested": suggested.isoformat(),
        "kept": rec.kept, "total": rec.total, "median_slip": rec.median_slip,
        "why": (f"Of your last {rec.total} {basis}, {rec.kept} {'was' if rec.kept == 1 else 'were'} on time; "
                f"the typical one landed {shift} day{'s' if shift != 1 else ''} late."),
    }


def as_json() -> dict:
    rep = report()
    pack = lambda r: {"kept": r.kept, "total": r.total, "rate": round(r.rate, 2), "median_slip": r.median_slip}
    return {"overall": pack(rep["overall"]),
            "by_kind": {k: pack(v) for k, v in sorted(rep["by_kind"].items())},
            "by_person": {k: pack(v) for k, v in sorted(rep["by_person"].items())},
            "by_weekday": {k: pack(v) for k, v in rep["by_weekday"].items()}}
