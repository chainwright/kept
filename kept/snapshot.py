"""A recorded morning, so a visitor sees Kept's work at once instead of waiting minutes for it.

`save()` copies the data directory after a real run on Nemotron into demo_snapshot/.
`restore()` puts it back, moving every date forward by whole weeks so the week still lines up
with today: "by Friday" stays a Friday, and the snapshot is at most six days old. Nothing in it
is edited by hand; the UI labels it as a recorded run and "Run morning loop" runs it live again.
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


def restore(today: date | None = None) -> dict:
    today = today or date.today()
    recorded = date.fromisoformat(json.loads((SNAP / META).read_text())["recorded_on"])
    days = weeks_shift(recorded, today)
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
        if f.suffix in (".json", ".jsonl", ".md", ".txt") and f.name != META:
            target.write_text(shift_text(f.read_text(), days, recorded))
        else:
            shutil.copy2(f, target)
    info = {"recorded_on": recorded.isoformat(), "shown_as": (recorded + timedelta(days=days)).isoformat(),
            "shifted_days": days}
    (dst / META).write_text(json.dumps(info))
    return info
