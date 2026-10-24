from kept import approvals, growth, store
from kept.seed import seed

ASK = {"subject": "Thank you!", "body": "Hi Noah, two catering inquiries on day one is fantastic! If you have a minute, a short review at https://g.page/r/alex-rivera-studio/review would mean a lot, or mention me to another owner who needs a site. Alex"}
POST = {"text": "Brooks Coffee went live this week. On day one the new site brought in 2 catering inquiries through the form, and customers say the menu is easy to read on their phones."}


def test_delighted_client_gets_a_review_ask_and_a_post_both_waiting(fake):
    seed(force=True)
    fake([("clearly delighted", lambda p: {"delighted": "Noah" in p, "quote": "we already got two catering inquiries"}),
          ("leave a short review", ASK), ("LinkedIn post", POST)])
    out = growth.moments()
    kinds = sorted(a["kind"] for a in approvals.pending())
    assert kinds == ["publish_post", "send_email"] and len(out["asks"]) == 1


def test_happy_client_with_open_work_is_not_asked_yet(fake):
    seed(force=True)
    fake([("clearly delighted", lambda p: {"delighted": "Maria" in p, "quote": "Thank you!! Maria"})])
    out = growth.moments()
    assert out["asks"] == [] and out["waiting"][0]["why"] == "the project isn't finished and paid yet"


def test_post_with_invented_numbers_or_unapproved_name_is_held_back(fake):
    seed(force=True)
    fake([("clearly delighted", lambda p: {"delighted": "Noah" in p, "quote": "we already got two catering inquiries"}),
          ("leave a short review", ASK),
          ("LinkedIn post", {"text": "Brooks Coffee saw a 40% jump in orders after launch."})])
    growth.moments()
    assert [a["kind"] for a in approvals.pending()] == ["send_email"]
    assert any("40%" in p for h in store.read_json("abstained.json", []) for p in h["problems"])


def test_review_ask_offering_something_in_return_is_held_back(fake):
    seed(force=True)
    fake([("clearly delighted", lambda p: {"delighted": "Noah" in p, "quote": "we already got two catering inquiries"}),
          ("leave a short review", {"subject": "x", "body": "Hi Noah, leave a review at https://g.page/r/alex-rivera-studio/review and get 10% off your next update! Alex"}),
          ("LinkedIn post", POST)])
    growth.moments()
    assert all(a["kind"] != "send_email" for a in approvals.pending())
