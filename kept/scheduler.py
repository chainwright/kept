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


def _hold_demo_day() -> dict | None:
    from . import snapshot
    try:
        info = snapshot.keep_current()
    except Exception as e:
        append_audit("job_failed", job="demo_day", error=f"{type(e).__name__}: {e}"[:300])
        return None
    if info and info.get("restored"):
        append_audit("job", job="demo_day", status="ok", note=f"recorded morning of {info['shown_as']} put back")
    return info


def start() -> BackgroundScheduler:
    global _sched
    if _sched:
        return _sched
    _sched = BackgroundScheduler(timezone=settings.timezone)
    if settings.demo:
        # The demo shows one recorded morning and its calendar stands still on that day (democlock). Daily and
        # hourly jobs would rewrite it against the real date, so they are off in the demo: no hourly mail sorting
        # happens there. Once an hour it only checks the recorded morning is still in place, and writes to the
        # activity log only when it had to put it back (an "ok" every hour crowded out everything else).
        _sched.add_job(_hold_demo_day, "interval", hours=1, id="demo_day")
        _sched.start()
        return _sched
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
