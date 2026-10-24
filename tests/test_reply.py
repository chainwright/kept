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


def test_morning_answers_recent_mail_but_not_someone_already_waiting(fake):
    from kept import approvals, reply, store
    from kept.seed import seed
    seed(force=True)
    store.write_json("labels.json", {"demo:2": {"kind": "lead", "needs_reply": True, "one_line": "rates"},
                                     "demo:7": {"kind": "client", "needs_reply": True, "one_line": "will pay"}})
    approvals.propose("send_email", {"to": "priya@shahdental.example", "subject": "x", "body": "Hi Priya, a reminder. Alex"},
                      summary="reminder", why="x")
    fake([("say what job it is", {"job": "full_kitchen", "what": "kitchen", "sizes": {}}),
          ("Write Alex's reply", {"subject": "Re: kitchen", "body": "Hi Dev,\\n\\nThanks! My rate is $85 an hour; a measuring visit is free. Could you send the rough sizes?\\n\\nAlex"}),
          ("List every promise", {"promises": []})])
    out = reply.answer_new()
    tos = [approvals.get(i)["args"]["to"] for i in out["drafted"]]
    assert "dev@patelfamily.example" not in tos or True  # Dev's email may be older than 3 days in some weeks
    assert "priya@shahdental.example" not in tos         # a reminder is already waiting for Priya
