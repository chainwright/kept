"""A recorded morning, so a visitor sees Kept's work at once instead of waiting minutes for it.

`save()` copies the data directory after a real run on Nemotron into demo_snapshot/.
`restore()` puts it back exactly as recorded, and the demo's calendar is held on the recorded day
(democlock), so a visitor in December sees the same Saturday, the same rent day and the same $116
gap as the write-up. Nothing in it is edited by hand; the UI labels it as a recorded run and
"Run morning loop" runs it live again. (`shift_text` can still move a copy by whole weeks; the
demo no longer does.)
"""
from __future__ import annotations

import json
import re
import shutil
from datetime import date, timedelta
from pathlib import Path

from .config import ROOT
from .store import data_dir

SNAP = ROOT / "demo_snapshot"
META = "snapshot.json"
_MONTHS = ["January", "February", "March", "April", "May", "June", "July", "August", "September",
           "October", "November", "December"]
_ISO = re.compile(r"\b(20\d\d)-(\d\d)-(\d\d)\b")
_WORD = re.compile(r"\b(" + "|".join(m[:3] + "(?:" + m[3:] + ")?" for m in _MONTHS) + r")\.? (\d{1,2})\b(,? 20\d\d)?")


def available() -> bool:
    return (SNAP / META).exists()


def meta() -> dict | None:
    p = data_dir() / META
    return json.loads(p.read_text()) if p.exists() else None


def save(src: Path | None = None, recorded_on: date | None = None) -> Path:
    src = src or data_dir()
    if SNAP.exists():
        shutil.rmtree(SNAP)
    shutil.copytree(src, SNAP, ignore=shutil.ignore_patterns("outbox", "*.lock"))
    (SNAP / META).write_text(json.dumps({"recorded_on": (recorded_on or date.today()).isoformat()}))
    return SNAP


def weeks_shift(recorded: date, today: date) -> int:
    return max(0, (today - recorded).days // 7) * 7


def shift_text(text: str, days: int, recorded: date) -> str:
    if not days:
        return text
    delta = timedelta(days=days)

    def iso(m):
        try:
            return (date(int(m[1]), int(m[2]), int(m[3])) + delta).isoformat()
        except ValueError:
            return m[0]

    def word(m):
        name, day, year = m[1], int(m[2]), m[3]
        month = next(i for i, full in enumerate(_MONTHS, 1) if full.startswith(name[:3]))
        y = int(re.sub(r"\D", "", year)) if year else recorded.year
        if not year and month < recorded.month - 6:
            y += 1  # "Jan 4" written in late October means next January
        try:
            d = date(y, month, day) + delta
        except ValueError:
            return m[0]
        out = (_MONTHS[d.month - 1] if len(name) > 3 else _MONTHS[d.month - 1][:3]) + ("." if m[0][len(name)] == "." else "")
        out += f" {d.day}"
        if year:
            out += ("," if year.startswith(",") else "") + f" {d.year}"
        return out

    return _WORD.sub(word, _ISO.sub(iso, text))


def restore(today: date | None = None, *, shift: bool = False) -> dict:
    """Put the recorded morning back. By default every date stays as recorded and the demo's "today" is the recorded
    day, so nothing drifts week to week. `shift=True` moves it forward by whole weeks to `today` (kept for tools)."""
    from . import democlock
    recorded = date.fromisoformat(json.loads((SNAP / META).read_text())["recorded_on"])
    days = weeks_shift(recorded, today or democlock.real_today()) if shift else 0
    dst = data_dir()
    for p in dst.iterdir():
        shutil.rmtree(p) if p.is_dir() else p.unlink()
    for f in SNAP.rglob("*"):
        rel = f.relative_to(SNAP)
        target = dst / Path(shift_text(str(rel), days, recorded))  # journal/YYYY-MM-DD.md
        if f.is_dir():
            target.mkdir(parents=True, exist_ok=True)
            continue
        target.parent.mkdir(parents=True, exist_ok=True)
        if f.name == "audit.jsonl":
            # mark the recorded morning's calls, so they don't count against today's budget
            lines = []
            for line in shift_text(f.read_text(), days, recorded).splitlines():
                if line.strip():
                    rec = json.loads(line)
                    rec["recorded"] = True
                    lines.append(json.dumps(rec, ensure_ascii=False))
            target.write_text("\n".join(lines) + "\n")
        elif f.suffix in (".json", ".jsonl", ".md", ".txt") and f.name != META:
            target.write_text(shift_text(f.read_text(), days, recorded))
        else:
            shutil.copy2(f, target)
    info = {"recorded_on": recorded.isoformat(), "shown_as": (recorded + timedelta(days=days)).isoformat(),
            "shifted_days": days}
    (dst / META).write_text(json.dumps(info))
    democlock.set_today(date.fromisoformat(info["shown_as"]))  # the demo's "today" is the morning it shows
    return info


def keep_current() -> dict | None:
    """Demo only: hold the demo's calendar on the recorded day. If the data was wiped, or was laid down by an older
    build that shifted dates by weeks, put the recorded morning back. Called at startup and hourly. The result says
    whether anything had to be restored, so the hourly check stays out of the activity log when nothing changed."""
    from . import democlock
    m = meta()
    if not available():
        return None
    recorded = json.loads((SNAP / META).read_text())["recorded_on"]
    if not m or m.get("shown_as") != recorded or m.get("shifted_days"):
        return {**restore(), "restored": True}
    democlock.set_today(date.fromisoformat(m["shown_as"]))
    return {**m, "restored": False}
