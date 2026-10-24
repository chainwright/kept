"""Kept runs on its own: the morning loop once a day, inbox triage every hour."""
from __future__ import annotations

from apscheduler.schedulers.background import BackgroundScheduler

from . import agent
from .config import settings
from .store import append_audit

_sched: BackgroundScheduler | None = None


def _safe(name, fn):
    def run():
        try:
            fn()
            append_audit("job", job=name, status="ok")
        except Exception as e:
            append_audit("job_failed", job=name, error=f"{type(e).__name__}: {e}"[:300])
    return run


def start() -> BackgroundScheduler:
    global _sched
    if _sched:
        return _sched
    _sched = BackgroundScheduler(timezone=settings.timezone)
    _sched.add_job(_safe("day", agent.run_day), "cron", hour=7, minute=30, id="day")
    _sched.add_job(_safe("triage", agent.triage_inbox), "cron", minute=5, id="triage")
    _sched.start()
    return _sched
