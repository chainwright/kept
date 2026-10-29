"""The demo's calendar stands still.

The demo shows one recorded morning (Alex's Tuesday). If the app read the real calendar, that morning would age a
little every day: promises would slip into the past, the cash forecast would start from a later day, and drafts
would be held back for dates that have "already passed". So in demo mode "today" is the day the recorded morning is
shown on, and it only moves when the snapshot itself moves forward a whole week.

install() swaps `date` and `datetime` inside Kept's own modules only (libraries keep the real ones). With no
frozen day set, both classes behave exactly like the real ones.
"""
from __future__ import annotations

import datetime as _dt

REAL_DATE = _dt.date
REAL_DATETIME = _dt.datetime
_frozen: REAL_DATE | None = None


def set_today(d) -> None:
    global _frozen
    _frozen = REAL_DATE(d.year, d.month, d.day) if d else None


def frozen() -> REAL_DATE | None:
    return _frozen


def real_today() -> REAL_DATE:
    return REAL_DATE.today()


class DemoDate(REAL_DATE):
    @classmethod
    def today(cls):
        t = _frozen or REAL_DATE.today()
        return cls(t.year, t.month, t.day)


class DemoDateTime(REAL_DATETIME):
    @classmethod
    def now(cls, tz=None):
        n = REAL_DATETIME.now(tz)
        if _frozen:
            n = n.replace(year=_frozen.year, month=_frozen.month, day=_frozen.day)
        return cls(n.year, n.month, n.day, n.hour, n.minute, n.second, n.microsecond, tzinfo=n.tzinfo)

    @classmethod
    def today(cls):
        return cls.now()


def install() -> list[str]:
    """Import every kept.* module, then point their `date` / `datetime` names at the demo classes."""
    import importlib
    import pkgutil
    import sys

    import kept
    for m in pkgutil.iter_modules(kept.__path__):
        if m.name not in ("democlock",):
            importlib.import_module(f"kept.{m.name}")
    patched = []
    for name, mod in list(sys.modules.items()):
        if not name.startswith("kept.") or mod is None or name == "kept.democlock":
            continue
        if getattr(mod, "date", None) is REAL_DATE:
            mod.date = DemoDate
            patched.append(name)
        if getattr(mod, "datetime", None) is REAL_DATETIME:
            mod.datetime = DemoDateTime
            patched.append(name)
    return sorted(set(patched))


def uninstall() -> None:
    """Back to the real calendar everywhere (tests)."""
    import sys
    set_today(None)
    for name, mod in list(sys.modules.items()):
        if name.startswith("kept.") and mod is not None:
            if getattr(mod, "date", None) is DemoDate:
                mod.date = REAL_DATE
            if getattr(mod, "datetime", None) is DemoDateTime:
                mod.datetime = REAL_DATETIME
