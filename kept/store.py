"""Plain-file storage. Everything Kept knows lives in files a person can open and read.

data/
  ledger.json        open and closed commitments
  approvals.json     actions waiting for the owner's Yes/No, and what happened after
  journal/DATE.md    what Kept did and decided each day (its working memory)
  notes.md           long-lived facts about the owner and their business
  audit.jsonl        every model call and every action, one JSON object per line
  outbox/            demo-mode mail that would have been sent
"""
from __future__ import annotations

import json
import os
import tempfile
import threading
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .config import settings

_lock = threading.RLock()


def data_dir() -> Path:
    d = settings.data_dir
    (d / "journal").mkdir(parents=True, exist_ok=True)
    (d / "outbox").mkdir(parents=True, exist_ok=True)
    return d


def now() -> datetime:
    return datetime.now(timezone.utc)


def now_iso() -> str:
    return now().isoformat(timespec="seconds")


def read_json(name: str, default: Any) -> Any:
    p = data_dir() / name
    with _lock:
        if not p.exists():
            return default
        return json.loads(p.read_text() or "null") or default


def write_json(name: str, value: Any) -> None:
    p = data_dir() / name
    with _lock:
        # write-then-rename, so a crash mid-write never leaves half a ledger behind
        fd, tmp = tempfile.mkstemp(dir=p.parent, prefix=p.name, suffix=".tmp")
        with os.fdopen(fd, "w") as f:
            json.dump(value, f, ensure_ascii=False, indent=1)
        os.replace(tmp, p)


def append_audit(kind: str, **fields: Any) -> dict:
    rec = {"ts": now_iso(), "kind": kind, **fields}
    with _lock, open(data_dir() / "audit.jsonl", "a") as f:
        f.write(json.dumps(rec, ensure_ascii=False) + "\n")
    return rec


def read_audit(limit: int = 200) -> list[dict]:
    p = data_dir() / "audit.jsonl"
    if not p.exists():
        return []
    lines = p.read_text().splitlines()[-limit:]
    return [json.loads(x) for x in lines if x.strip()]


def journal(line: str) -> None:
    day = now().astimezone().strftime("%Y-%m-%d")
    p = data_dir() / "journal" / f"{day}.md"
    with _lock:
        new = not p.exists()
        with open(p, "a") as f:
            if new:
                f.write(f"# {day}\n\n")
            f.write(f"- {now().astimezone().strftime('%H:%M')} {line}\n")


def read_journal(days: int = 2) -> str:
    files = sorted((data_dir() / "journal").glob("*.md"))[-days:]
    return "\n".join(f.read_text() for f in files)


def read_notes() -> str:
    p = data_dir() / "notes.md"
    return p.read_text() if p.exists() else ""
