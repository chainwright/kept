"""The commitment ledger: every promise stays visible until it is answered.

An open item can only leave the ledger with an explicit resolution: done (with
evidence), dropped (with a reason), or handed to someone. "I forgot" is not a
state. The morning brief always starts with what is still open.
"""
from __future__ import annotations

import uuid
from datetime import date, datetime
from typing import Any

from .store import append_audit, journal, now_iso, read_json, write_json

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


def add(text: str, *, who: str = "", due: str | None = None, source: str = "",
        origin: str = "owner", contact: str = "", direction: str = "i_owe", quote: str = "") -> dict:
    """direction: 'i_owe' (the owner promised) or 'owed_to_me' (someone promised the owner)."""
    text = text.strip()
    if not text:
        raise LedgerError("a commitment needs words")
    if direction not in DIRECTIONS:
        raise LedgerError(f"direction must be one of {DIRECTIONS}")
    rows = _all()
    # the same promise mentioned twice is still one promise
    for r in rows:
        if r["status"] == "open" and r["text"].lower() == text.lower() and r.get("who") == who:
            return r
    row = {"id": uuid.uuid4().hex[:8], "text": text, "who": who, "due": due, "source": source,
           "origin": origin, "contact": contact, "direction": direction, "quote": quote, "status": "open", "created": now_iso(), "history": []}
    rows.append(row)
    write_json(FILE, rows)
    append_audit("ledger_add", id=row["id"], text=text, who=who, due=due, origin=origin)
    journal(f"New commitment {row['id']}: {text}" + (f" (to {who})" if who else "") + (f", due {due}" if due else ""))
    return row


def close(item_id: str, resolution: str, note: str) -> dict:
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


def touch(item_id: str, event: str) -> None:
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
