from kept import approvals, store, tryit
from kept.seed import seed

LEAD = ("new", "Website", "Hi Alex, I need a site for my salon. What do you charge?")


def _fake(fake, reply_body):
    return fake([
        ("Classify this email", {"kind": "lead", "needs_reply": True, "one_line": "asks for a price"}),
        ("Find two kinds of promise", {"mine": [], "theirs": []}),
        ("Write Alex's reply", {"subject": "Re: Website", "body": reply_body}),
        ("List every promise", {"promises": []}),
    ])


def test_reply_with_only_the_hourly_rate_waits_for_yes(fake):
    seed(force=True)
    _fake(fake, "Hi Jo,\n\nMy rate is $85 an hour. Could we do a short call to scope it?\n\nAlex")
    r = tryit.handle(*LEAD, name="Jo Rivera", email="jo@example.com")
    a = r["reply"]["approval"]
    assert a["status"] == "pending" and a["args"]["to"] == "jo@example.com"
    assert not list((store.data_dir() / "outbox").glob("*.json"))


def test_reply_that_invents_a_project_price_is_held_back(fake):
    seed(force=True)
    _fake(fake, "Hi Jo,\n\nA new kitchen would be $3,333 all in.\n\nAlex")
    r = tryit.handle(*LEAD, name="Jo Rivera", email="jo@example.com")
    assert not (r["reply"] or {}).get("approval")
    assert any("aren't in Alex's records" in p for h in r["held_back"] for p in h["problems"])
    assert not [a for a in approvals.pending() if a["args"].get("to") == "jo@example.com"]
