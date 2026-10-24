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
    def hourly():
        from .reply import answer_new
        report = agent.triage_inbox()
        answer_new(list(report.get("labels", {}).keys()))
    _sched.add_job(_safe("triage", hourly), "cron", minute=5, id="triage")
    from . import learn
    _sched.add_job(_safe("learn", learn.propose_rules), "cron", day_of_week="mon", hour=7, id="learn")
    _sched.start()
    return _sched
