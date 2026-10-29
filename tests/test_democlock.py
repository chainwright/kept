"""The demo's calendar stands still: what a judge sees weeks later is the morning the write-up describes."""
from datetime import date

import pytest

from kept import democlock, money, snapshot


@pytest.fixture
def frozen_demo():
    democlock.install()
    yield
    democlock.uninstall()


@pytest.mark.skipif(not snapshot.available(), reason="needs the recorded morning in demo_snapshot/")
@pytest.mark.parametrize("real_day", [date(2026, 10, 28), date(2026, 11, 3), date(2026, 11, 12), date(2026, 12, 9)])
def test_the_recorded_morning_tells_the_same_story_on_any_day(frozen_demo, real_day, monkeypatch):
    monkeypatch.setattr(democlock, "real_today", lambda: real_day)
    info = snapshot.keep_current()
    shown = date.fromisoformat(info["shown_as"])
    assert shown <= real_day and (real_day - shown).days < 7 and shown.weekday() == date(2026, 10, 24).weekday()
    assert money.date.today() == shown  # the app's "today" is the shown morning, not the real date
    short = money.forecast()["short"]
    assert short["gap"] == 116.0 and short["because"] == "Workshop rent"


def test_unfrozen_classes_are_the_real_calendar(frozen_demo):
    democlock.set_today(None)
    assert democlock.DemoDate.today() == date.today()
    democlock.set_today(date(2026, 10, 24))
    assert democlock.DemoDate.today() == date(2026, 10, 24)
    assert democlock.DemoDateTime.now().date() == date(2026, 10, 24)
