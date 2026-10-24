from datetime import date

from kept import approvals, offers, store
from kept.seed import seed

T = date(2026, 10, 24)


def test_calendar_knows_the_season():
    ids = [o["id"] for o in offers.calendar(T)]
    assert "black-friday-2026" in ids and "new-year-2027" in ids


def test_who_is_eligible_and_why_not():
    seed(force=True)
    eligible, skipped = offers.candidates(date.today())
    names = {c["client"] for c in eligible}
    why = {c["client"]: c["why_not"] for c in skipped}
    assert "Lucia Ferri" in names                     # paid early, nothing ordered lately
    assert names == {"Lucia Ferri"}
    assert why["Jordan Kim"].startswith("wrote to you this week")
    assert why["Priya Shah"] == "owes an overdue invoice"
    assert why["Maria Lopez"] == "has a project in progress"


def _ultra(**over):
    bf = next(o for o in offers.calendar(date.today()) if o["id"].startswith("black-friday"))
    d = {"client": "Lucia Ferri", "make_offer": True, "occasion_id": bf["id"],
         "what": "Holiday gift-guide page", "price": 950, "discount_pct": 10,
         "book_by": (bf["date"] - __import__("datetime").timedelta(days=7)).isoformat(), "why": "their busiest weekend"}
    d.update(over)
    return {"offers": [d]}


def test_offer_inside_the_rules_waits_for_yes(fake):
    seed(force=True)
    fake([("seasonal offer is worth making", _ultra()),
          ("ahead of", {"subject": "Black Friday", "body": "Hi Lucia, Black Friday is your biggest weekend. A gift-guide page would help shoppers find things fast; $950 (10% off) if booked a week before. Want to chat? Alex"})])
    res = offers.propose()
    assert len(res["offers"]) == 1 and approvals.pending()[0]["args"]["to"] == "lucia@ferriboutique.example"


def test_discount_over_the_limit_or_below_floor_is_held_back(fake):
    seed(force=True)
    fake([("seasonal offer is worth making", _ultra(discount_pct=30))])
    assert offers.propose()["offers"] == []
    fake([("seasonal offer is worth making", _ultra(price=500, discount_pct=0))])
    assert offers.propose()["offers"] == []
    probs = [p for h in store.read_json("abstained.json", []) for p in h["problems"]]
    assert any("outside your limit" in p for p in probs) and any("below your minimum" in p for p in probs)


def test_email_with_unapproved_discount_is_held_back(fake):
    seed(force=True)
    fake([("seasonal offer is worth making", _ultra()),
          ("ahead of", {"subject": "x", "body": "Hi Jordan, $950 with 25% off, last chance! Alex"})])
    assert offers.propose()["offers"] == []


def test_no_offer_to_someone_who_just_wrote():
    from datetime import date
    from kept import offers, store
    from kept.seed import seed
    seed(force=True)
    _, skipped = offers.candidates(date.today())
    why = {s["client"]: s["why_not"] for s in skipped}
    assert "Jordan Kim" in why  # Jordan wrote this week asking about the form fix
