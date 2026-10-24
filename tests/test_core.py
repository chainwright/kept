import json
from datetime import date, timedelta

import pytest

from kept import approvals, ledger, store
from kept.llm import BudgetExceeded, parse_json, router
from kept.tools import mail  # registers send_email
from kept.validators import grounded, plausible_due, sendable_text, shape


# ---------------------------------------------------------------- validators
def test_grounded_accepts_real_quote_and_rejects_invented_one():
    src = {"web:1": "Stripe said on Tuesday that fees for small merchants will rise to 3.1% in January."}
    ok = grounded([{"source": "web:1", "quote": "fees for small merchants will rise to 3.1%"}], src)
    assert ok
    bad = grounded([{"source": "web:1", "quote": "fees will fall to 1% for everyone next week"}], src)
    assert not bad and "not in source" in bad.problems[0]
    ghost = grounded([{"source": "web:9", "quote": "anything at all, long enough"}], src)
    assert not ghost and "never fetched" in ghost.problems[0]


def test_sendable_text_catches_template_holes_and_missing_name():
    assert not sendable_text("Hi [Name], thanks!")
    assert not sendable_text("Hi there, thanks!", must_mention=["Maria"])
    assert sendable_text("Hi Maria, the proposal is attached.", must_mention=["Maria"])


def test_plausible_due():
    today = date(2026, 10, 24)
    assert plausible_due("2026-10-30", today=today)
    assert not plausible_due("2024-01-01", today=today)
    assert not plausible_due("next tuesday", today=today)
    assert plausible_due(None, today=today)


def test_shape():
    assert shape({"a": "x", "b": True}, {"a": str, "b": bool})
    assert not shape({"a": 1}, {"a": str, "b": bool})


def test_parse_json_tolerates_fences_and_thinking():
    assert parse_json('<think>hmm</think>```json\n{"x": 1}\n```') == {"x": 1}
    assert parse_json('Sure! {"x": [1,2]} hope that helps') == {"x": [1, 2]}


# ---------------------------------------------------------------- ledger
def test_ledger_needs_a_reason_to_close_and_dedupes():
    a = ledger.add("Send Maria the revised quote", who="Maria", due="2026-10-25")
    b = ledger.add("send maria the revised quote", who="Maria")
    assert a["id"] == b["id"]
    with pytest.raises(ledger.LedgerError):
        ledger.close(a["id"], "done", "")
    with pytest.raises(ledger.LedgerError):
        ledger.close(a["id"], "forgot", "it happened")
    ledger.close(a["id"], "done", "Sent v2 of the quote on Friday")
    assert ledger.items("open") == []


def test_overdue_sorts_first():
    today = date.today()
    ledger.add("later thing", due=(today + timedelta(days=5)).isoformat())
    late = ledger.add("late thing", due=(today - timedelta(days=2)).isoformat())
    assert ledger.open_sorted(today)[0]["id"] == late["id"]


# ---------------------------------------------------------------- approval gate
def test_gate_blocks_unapproved_actions():
    req = approvals.propose("send_email", {"to": "a@b.co", "subject": "hi", "body": "hello"},
                            summary="email a@b.co", why="test")
    with pytest.raises(approvals.GateError):
        approvals.execute(req["id"])
    with pytest.raises(approvals.GateError):
        approvals.run_unguarded("send_email", req["args"])
    assert list((store.data_dir() / "outbox").iterdir()) == []


def test_yes_runs_the_action_in_demo_outbox_and_no_does_not():
    yes = approvals.propose("send_email", {"to": "a@b.co", "subject": "s", "body": "b"}, summary="x", why="y")
    no = approvals.propose("send_email", {"to": "c@d.co", "subject": "s", "body": "b"}, summary="x", why="y")
    assert approvals.decide(yes["id"], True)["status"] == "done"
    assert approvals.decide(no["id"], False)["status"] == "rejected"
    sent = [json.loads(p.read_text())["to"] for p in (store.data_dir() / "outbox").iterdir()]
    assert sent == ["a@b.co"]
    with pytest.raises(approvals.GateError):
        approvals.decide(yes["id"], True)  # can't approve twice


# ---------------------------------------------------------------- routing + budget
def test_routing_picks_the_right_nemotron_and_logs_cost(fake):
    fake([])
    r = router.ask("classify", [{"role": "user", "content": "x"}], purpose="t")
    assert "Nano" in r.model and r.tier == "nano"
    r = router.ask("judge", [{"role": "user", "content": "x"}], purpose="t")
    assert "Ultra" in r.model
    rows = [x for x in store.read_audit() if x["kind"] == "llm"]
    assert len(rows) == 2 and rows[1]["usd"] > rows[0]["usd"]


def test_budget_stops_calls(fake, monkeypatch):
    fake([])
    from kept.config import settings
    monkeypatch.setattr(settings, "daily_budget_usd", 0.0)
    with pytest.raises(BudgetExceeded):
        router.ask("classify", [{"role": "user", "content": "x"}], purpose="t")


def test_one_line_email_signed_by_owner_is_not_a_wrong_greeting():
    from kept.validators import honest_email
    assert honest_email("Hi Priya, any news on invoice #118? Thanks, Alex", recipient_first="Priya", owner_first="Alex")
    assert not honest_email("Hi Alex, any news?", recipient_first="Priya", owner_first="Alex")


def test_parse_json_accepts_python_style_dicts_safely():
    assert parse_json("{'rules': [{'rule': 'x', 'ok': True}]}") == {"rules": [{"rule": "x", "ok": True}]}
    import pytest as _p
    with _p.raises(Exception):
        parse_json("{'a': __import__('os')}")
