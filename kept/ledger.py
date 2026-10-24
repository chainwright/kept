"""The commitment ledger: every promise stays visible until it is answered.

An open item can only leave the ledger with an explicit resolution: done (with
evidence), dropped (with a reason), or handed to someone. "I forgot" is not a
state. The morning brief always starts with what is still open.
"""
from __future__ import annotations

import re
import uuid
from datetime import date, datetime
from typing import Any

from .store import append_audit, journal, locked, now_iso, read_json, write_json

FILE = "ledger.json"
RESOLUTIONS = ("done", "dropped", "handed_off")
DIRECTIONS = ("i_owe", "owed_to_me")


class LedgerError(ValueError):
    pass


def _all() -> list[dict]:
    return read_json(FILE, [])


def items(status: str | None = None) -> list[dict]:
    rows = _all()
    return [r for r in rows if status is None or r["status"] == status]


def get(item_id: str) -> dict:
    for r in _all():
        if r["id"] == item_id:
            return r
    raise LedgerError(f"no commitment {item_id}")


def _add(text: str, *, who: str = "", due: str | None = None, source: str = "",
        origin: str = "owner", contact: str = "", direction: str = "i_owe", quote: str = "") -> dict:
    """direction: 'i_owe' (the owner promised) or 'owed_to_me' (someone promised the owner)."""
    text = text.strip()
    if not text:
        raise LedgerError("a commitment needs words")
    if direction not in DIRECTIONS:
        raise LedgerError(f"direction must be one of {DIRECTIONS}")
    rows = _all()
    # the same promise mentioned twice is still one promise
    def same(r):
        if r["status"] != "open" or r.get("who") != who:
            return False
        if r["text"].lower() == text.lower():
            return True
        # "Pay invoice #118" and "Priya pays invoice #118" are one promise
        refs = set(re.findall(r"#\s?(\d+)", text))
        return bool(refs) and refs == set(re.findall(r"#\s?(\d+)", r["text"])) and \
            (r.get("direction") or "i_owe") == direction

    for r in rows:
        if same(r):
            if due and due != r.get("due"):
                # promised again with a new date: keep the old one in the history, so a slipped
                # promise is visible ("was due Oct 22, now promised for Oct 28")
                r.setdefault("history", []).append({"ts": now_iso(), "event": f"promised again for {due} (was {r.get('due')})"})
                r["due"] = due
                write_json(FILE, rows)
                journal(f"{who or 'Someone'} promised '{text}' again, now for {due}")
            return r
    row = {"id": uuid.uuid4().hex[:8], "text": text, "who": who, "due": due, "source": source,
           "origin": origin, "contact": contact, "direction": direction, "quote": quote, "status": "open", "created": now_iso(), "history": []}
    rows.append(row)
    write_json(FILE, rows)
    append_audit("ledger_add", id=row["id"], text=text, who=who, due=due, origin=origin)
    journal(f"New commitment {row['id']}: {text}" + (f" (to {who})" if who else "") + (f", due {due}" if due else ""))
    return row


def _close(item_id: str, resolution: str, note: str) -> dict:
    """Close only with a reason a person can read later."""
    if resolution not in RESOLUTIONS:
        raise LedgerError(f"resolution must be one of {RESOLUTIONS}")
    if len(note.strip()) < 5:
        raise LedgerError("closing a commitment needs a short note: what happened")
    rows = _all()
    for r in rows:
        if r["id"] == item_id:
            if r["status"] != "open":
                raise LedgerError(f"{item_id} is already {r['status']}")
            r["status"] = resolution
            r["closed"] = now_iso()
            r["note"] = note.strip()
            write_json(FILE, rows)
            append_audit("ledger_close", id=item_id, resolution=resolution, note=note)
            journal(f"Closed {item_id} as {resolution}: {note}")
            return r
    raise LedgerError(f"no commitment {item_id}")


def _touch(item_id: str, event: str) -> None:
    rows = _all()
    for r in rows:
        if r["id"] == item_id:
            r.setdefault("history", []).append({"ts": now_iso(), "event": event})
            write_json(FILE, rows)
            return


def days_overdue(row: dict, today: date | None = None) -> int:
    if not row.get("due"):
        return 0
    today = today or date.today()
    try:
        d = datetime.fromisoformat(row["due"][:10]).date()
    except ValueError:
        return 0
    return max(0, (today - d).days)


def direction(row: dict) -> str:
    return row.get("direction") or "i_owe"


def open_sorted(today: date | None = None, which: str | None = None) -> list[dict[str, Any]]:
    """Overdue first, then by due date, then oldest. which: 'i_owe', 'owed_to_me' or None for both."""
    rows = [r for r in items("open") if which is None or direction(r) == which]
    return sorted(rows, key=lambda r: (-days_overdue(r, today), r.get("due") or "9999", r["created"]))


def add(*a, **k) -> dict:
    with locked():
        return _add(*a, **k)


def close(*a, **k) -> dict:
    with locked():
        return _close(*a, **k)


def touch(*a, **k) -> None:
    with locked():
        return _touch(*a, **k)

