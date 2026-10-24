from kept import approvals, rescue
from kept.seed import seed


def test_slow_month_gets_an_ad_plan_inside_the_owners_budget(fake, monkeypatch):
    seed(force=True)
    from kept.tools import search
    monkeypatch.setattr(search, "search", lambda q, **k: [])
    fake([("Rank the candidates", {"steps": []}),
          ("short local ad", {"headline": "From tired to bright", "text": "Send us a photo of your kitchen for a free estimate.",
                              "why_now": "Rent is $116 short on the 1st; $10 a day for 7 days ($70) to find one kitchen job."})])
    out = rescue.plan()
    ad = approvals.get(out["ad"])
    assert ad["kind"] == "ad_plan" and ad["status"] == "pending" and ad["args"]["total"] == 70


def test_ad_plan_with_made_up_numbers_is_held_back(fake, monkeypatch):
    seed(force=True)
    from kept.tools import search
    monkeypatch.setattr(search, "search", lambda q, **k: [])
    fake([("Rank the candidates", {"steps": []}),
          ("short local ad", {"headline": "50% off kitchens", "text": "Only $999!", "why_now": "Spend $500 now."})])
    out = rescue.plan()
    assert out["ad"] is None
