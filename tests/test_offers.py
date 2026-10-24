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
    assert "Jordan Kim" in names                      # paid on time, nothing ordered lately
    assert why["Priya Shah"] == "owes an overdue invoice"
    assert why["Maria Lopez"] == "has a project in progress"


def _ultra(**over):
    d = {"client": "Jordan Kim", "make_offer": True, "occasion_id": f"new-year-{date.today().year + 1}",
         "what": "New Year class-pass landing page", "price": 950, "discount_pct": 10,
         "book_by": f"{date.today().year}-12-10", "why": "January is their busiest month"}
    d.update(over)
    return {"offers": [d]}


def test_offer_inside_the_rules_waits_for_yes(fake):
    seed(force=True)
    fake([("seasonal offer is worth making", _ultra()),
          ("ahead of", {"subject": "January sign-ups", "body": "Hi Jordan, January is when new students show up. A class-pass landing page would catch them; $950 (10% off) if booked by December 10. Want to chat? Alex"})])
    res = offers.propose()
    assert len(res["offers"]) == 1 and approvals.pending()[0]["args"]["to"] == "jordan@kimyoga.example"


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
