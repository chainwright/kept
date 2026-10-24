from kept import store, tryit
from kept.seed import seed


def test_a_visitors_email_is_handled_alone_and_waits_for_yes(fake):
    seed(force=True)
    fake([
        ("Classify this email", {"kind": "client", "needs_reply": True, "one_line": "wants a gift card page"}),
        ("agreement", {"requests": [{"request": "gift card page", "email_quote": "add a gift card page",
                                      "verdict": "out_of_scope", "agreement_quote": "online ordering",
                                      "reason": "new feature", "hours_low": 4, "hours_high": 6}]}),
        ("Find two kinds of promise", {"mine": [{"text": "Send Maria the menu PDF", "due": None,
                                                 "quote": "send the menu PDF"}], "theirs": []}),
        ("delighted", {"delighted": False, "quote": ""}),
    ])
    r = tryit.handle("maria", "Gift cards", "Hi Alex, could you add a gift card page? And send the menu PDF please. Maria")
    assert r["label"]["kind"] == "client"
    assert r["mail"]["id"].startswith("you:")
    assert any(p["text"] == "Send Maria the menu PDF" for p in r["promises"])
    assert all(a["status"] == "pending" for a in r["approvals"])
    assert not list((store.data_dir() / "outbox").glob("*.json"))  # nothing sent


def test_new_contact_needs_a_real_looking_address():
    seed(force=True)
    import pytest
    with pytest.raises(ValueError):
        tryit.handle("new", "hi", "Hello there, I need a website", name="Jo", email="not-an-address")


def test_a_bad_photo_leaves_nothing_behind():
    import json
    seed(force=True)
    before = len(json.loads((store.data_dir() / "inbox.json").read_text()))
    import pytest
    with pytest.raises(ValueError):
        tryit.handle("maria", "photo", "Hello Alex, photo attached", image="data:text/html;base64,PGgxPg==")
    assert len(json.loads((store.data_dir() / "inbox.json").read_text())) == before
