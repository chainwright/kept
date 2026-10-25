"""A quiet lead gets one gentle check-in a week later, inside the rules."""
from datetime import date, timedelta

from kept import approvals, estimate, followups
from kept.store import write_json


def _lead(days_ago: int, last_is_ours: bool = True):
    d = (date.today() - timedelta(days=days_ago + 1)).isoformat()
    write_json("inbox.json", [{"id": "m1", "from": "Jo Rivera <jo@riverahome.example>", "subject": "Our old kitchen",
                               "date": d, "ts": f"{d}T09:00:00+00:00", "body": "What would a new kitchen cost?"}])
    estimate.remember("jo@riverahome.example", {"low": 11500, "high": 14100, "mid": 12800, "lines": []}, "full_kitchen")
    if last_is_ours:
        a = approvals.propose("send_email", {"to": "jo@riverahome.example", "subject": "Re: kitchen", "body": "Hi Jo, about $11,500 to $14,100."},
                              summary="reply", why="x")
        approvals.decide(a["id"], True)
        rows = __import__("kept.store", fromlist=["read_json"]).read_json(approvals.FILE, [])
        for r in rows:
            r["created"] = r["finished"] = f"{(date.today() - timedelta(days=days_ago)).isoformat()}T10:00:00+00:00"
        write_json(approvals.FILE, rows)


GOOD = {"subject": "How's the kitchen thinking going?", "body": "Hi Jo,\n\nJust checking in on the kitchen: the estimate "
        "was about $11,500 to $14,100. Happy to answer questions or measure for free. If the timing isn't right, no problem.\n\nAlex"}


def test_a_week_of_silence_after_an_estimate_gets_one_gentle_check_in(fake):
    _lead(8)
    fake([("check-in", GOOD)])
    out = followups.propose()
    assert len(out["drafted"]) == 1
    assert followups.propose()["drafted"] == []          # never twice


def test_too_soon_or_their_turn_means_no_nudge(fake):
    _lead(3)
    ok, skipped = followups.candidates()
    assert not ok and "day(s)" in skipped[0]["why_not"]


def test_a_check_in_with_a_new_price_or_no_easy_way_out_is_held(fake):
    _lead(8)
    fake([("check-in", {"subject": "s", "body": "Hi Jo, I can do it for $9,999 this week only.\n\nAlex"})])
    assert followups.propose()["drafted"] == []
