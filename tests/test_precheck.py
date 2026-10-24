from datetime import date, timedelta

from kept import ledger, precheck, store
from tests.test_calibration import _closed


def _quote_history():
    base = date(2026, 9, 4)
    for i, late in enumerate([2, 3, 2, 0, 2]):
        due = base + timedelta(weeks=i)
        _closed(f"Send the quote to client {i}", due, due + timedelta(days=late))


import datetime as _dt
import pytest


@pytest.fixture(autouse=True)
def monday_nov_2(monkeypatch):
    """'by Friday' said on Monday Nov 2, 2026 means Friday Nov 6."""
    class FakeDate(_dt.date):
        @classmethod
        def today(cls):
            return cls(2026, 11, 2)
    monkeypatch.setattr(precheck, "date", FakeDate)


DRAFT = ("Hi Dev, thanks for reaching out! I'll send you my rates and a rough timeline by Friday. "
         "Looking forward to working together on the landscaping site.")


def test_finds_the_promise_and_suggests_a_realistic_day(fake):
    _quote_history()
    fri = "2026-11-06"
    fake([("is about to send", {"promises": [{"text": "send rates and timeline (quote)", "due": fri,
                                               "when_words": "by Friday", "quote": "I'll send you my rates and a rough timeline by Friday"}]}),
          ("Rewrite this message", {"text": DRAFT.replace("by Friday", "by Monday")})])
    res = precheck.check(DRAFT, "Dev")
    p = res["promises"][0]
    assert p["advice"]["suggested"] == "2026-11-09"
    assert res["rewrite"]["ok"] and "by Monday" in res["rewrite"]["text"]


def test_rewrite_that_changes_more_than_the_date_is_rejected(fake):
    _quote_history()
    fake([("is about to send", {"promises": [{"text": "send a quote", "due": "2026-11-06", "when_words": "by Friday",
                                               "quote": "I'll send you my rates and a rough timeline by Friday"}]}),
          ("Rewrite this message", {"text": "Hi Dev, I'll send the quote by Monday."})])
    rw = precheck.check(DRAFT, "Dev")["rewrite"]
    assert not rw["ok"] and any("dropped" in p or "length" in p for p in rw["problems"])


def test_invented_promise_is_not_reported(fake):
    fake([("is about to send", {"promises": [{"text": "build a logo", "due": None, "when_words": "",
                                               "quote": "I will also design a free logo for you"}]})])
    assert precheck.check(DRAFT, "Dev")["promises"] == []


def test_warns_about_other_promises_due_the_same_day(fake):
    ledger.add("Fix Jordan's contact form", who="Jordan", due="2026-11-06")
    fake([("is about to send", {"promises": [{"text": "send rates", "due": "2026-11-06", "when_words": "by Friday",
                                               "quote": "I'll send you my rates and a rough timeline by Friday"}]})])
    p = precheck.check(DRAFT, "Dev")["promises"][0]
    assert p["same_day"] == ["Fix Jordan's contact form"]


def test_code_resolves_weekday_words_not_the_model(fake, monkeypatch, monday_nov_2):
    import datetime as dt
    from kept import precheck as pc
    class FakeDate(dt.date):
        @classmethod
        def today(cls): return cls(2026, 10, 24)  # Saturday
    monkeypatch.setattr(pc, "date", FakeDate)
    fake([("is about to send", {"promises": [{"text": "send rates", "due": "2026-10-27", "when_words": "by Friday",
                                               "quote": "I'll send you my rates and a rough timeline by Friday"}]})])
    p = pc.check(DRAFT, "Dev")["promises"][0]
    assert p["due"] == "2026-10-30" and p["model_due"] == "2026-10-27"


def test_short_quote_falls_back_to_the_promise_text_if_it_is_in_the_draft(fake):
    fake([("is about to send", {"promises": [{"text": "I'll send you my rates and a rough timeline by Friday",
                                               "due": None, "when_words": "by Friday", "quote": "by Friday"}]})])
    p = precheck.check(DRAFT, "Dev")["promises"]
    assert len(p) == 1 and p[0]["quote"].startswith("I'll send you my rates")
