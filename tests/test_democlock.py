"""The demo's calendar stands still: what a judge sees weeks later is the morning the write-up describes."""
from datetime import date

import pytest

from kept import democlock, money, snapshot, store


@pytest.fixture
def frozen_demo():
    democlock.install()
    yield
    democlock.uninstall()


needs_snapshot = pytest.mark.skipif(not snapshot.available(), reason="needs the recorded morning in demo_snapshot/")
RECORDED = date(2026, 10, 24)


@needs_snapshot
@pytest.mark.parametrize("real_day", [date(2026, 10, 28), date(2026, 10, 31), date(2026, 11, 3), date(2026, 11, 12),
                                      date(2026, 12, 9), date(2026, 12, 15)])
def test_the_recorded_morning_tells_the_same_story_on_any_day(frozen_demo, real_day, monkeypatch):
    """Held on the recorded Saturday for good: rent day stays the 1st, the gap stays $116, in any week of judging."""
    monkeypatch.setattr(democlock, "real_today", lambda: real_day)
    info = snapshot.keep_current()
    assert info["shown_as"] == RECORDED.isoformat() and not info["shifted_days"]
    assert money.date.today() == RECORDED  # the app's "today" is the recorded morning, not the real date
    short = money.forecast()["short"]
    assert short == {"date": "2026-11-01", "gap": 116.0, "because": "Workshop rent"}
    assert "2026-11-01" in (store.data_dir() / "money.json").read_text()  # the files themselves aren't moved


@needs_snapshot
def test_the_hourly_check_is_silent_unless_it_puts_the_morning_back(frozen_demo, monkeypatch):
    from kept import scheduler
    snapshot.restore()
    before = len(store.read_audit(10000))
    for real_day in (date(2026, 10, 30), date(2026, 11, 7), date(2026, 12, 2)):
        monkeypatch.setattr(democlock, "real_today", lambda d=real_day: d)
        assert scheduler._hold_demo_day()["restored"] is False
    assert len(store.read_audit(10000)) == before  # 24 checks a day used to add 24 "ok" rows to the activity card

    # a build that shifted dates by weeks left a moved copy behind: put the recorded morning back, and say so once
    snapshot.restore(today=date(2026, 11, 9), shift=True)
    assert snapshot.meta()["shown_as"] == "2026-11-07"
    info = scheduler._hold_demo_day()
    assert info["restored"] is True and snapshot.meta()["shown_as"] == RECORDED.isoformat()
    assert democlock.frozen() == RECORDED
    logged = [a for a in store.read_audit(10000) if a.get("job") == "demo_day"]
    assert len(logged) == 1 and "put back" in logged[0]["note"]
    assert scheduler._hold_demo_day()["restored"] is False


def test_activity_card_skips_hourly_checks_and_folds_repeats():
    from kept.web import _activity
    audit = [{"ts": "2026-10-24T07:00:00+00:00", "kind": "ledger_add", "text": "Quote for Maria"}]
    audit += [{"ts": f"2026-10-24T{h:02d}:05:00+00:00", "kind": "job", "job": "demo_week", "status": "ok"} for h in range(8, 20)]
    audit += [{"ts": f"2026-10-24T20:0{i}:00+00:00", "kind": "llm_refused", "reason": "daily budget $5.00 reached"}
              for i in range(3)]
    rows = _activity(audit)
    assert [r["kind"] for r in rows] == ["llm_refused", "ledger_add"]
    assert rows[0]["repeats"] == 3 and rows[0]["ts"] == "2026-10-24T20:02:00+00:00"


@needs_snapshot
def test_the_page_gets_the_demo_day_and_clock(frozen_demo):
    from fastapi.testclient import TestClient
    from kept import web
    snapshot.restore()
    st = TestClient(web.app).get("/api/state").json()  # no lifespan: nothing is scheduled, no model is called
    assert st["today"] == RECORDED.isoformat() and st["now"].startswith(RECORDED.isoformat())
    assert st["cash"]["short"]["date"] == "2026-11-01"


def test_unfrozen_classes_are_the_real_calendar(frozen_demo):
    democlock.set_today(None)
    assert democlock.DemoDate.today() == date.today()
    democlock.set_today(date(2026, 10, 24))
    assert democlock.DemoDate.today() == date(2026, 10, 24)
    assert democlock.DemoDateTime.now().date() == date(2026, 10, 24)


def test_the_daily_budget_is_a_real_day_even_when_the_demo_calendar_stands_still(frozen_demo, fake, monkeypatch):
    """A frozen demo stamps every call with the recorded day. The budget must still reset each real day, or a $5
    daily cap becomes a weekly one and a busy judging week finds the demo "out of budget" for days."""
    from kept import llm, store
    from kept.config import settings

    fake([("", {"ok": True})])
    democlock.set_today(date(2026, 10, 24))
    monkeypatch.setattr(settings, "daily_budget_usd", 0.00001)  # one fake Nano call (100 in, 50 out: $0.000018) fills it
    day = {"v": "2026-11-03"}
    monkeypatch.setattr(llm, "real_utc_day", lambda: day["v"])

    llm.router.ask("classify", [{"role": "user", "content": "x"}], purpose="t", json_mode=True)
    call = [r for r in store.read_audit() if r["kind"] == "llm"][-1]
    assert call["ts"].startswith("2026-10-24") and call["paid_day"] == "2026-11-03"
    with pytest.raises(llm.BudgetExceeded):
        llm.router.ask("classify", [{"role": "user", "content": "x"}], purpose="t", json_mode=True)

    day["v"] = "2026-11-04"  # next real day, same frozen demo day
    assert llm.router.spent_today() == 0
    llm.router.ask("classify", [{"role": "user", "content": "x"}], purpose="t", json_mode=True)
