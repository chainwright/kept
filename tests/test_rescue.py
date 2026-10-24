from datetime import date

from kept import approvals, rescue, store
from kept.seed import seed

T = date.today()


def _world(monkeypatch, fake, ultra_steps, prospect_reply=None, pages=None):
    seed(force=True)
    from kept.tools import search
    monkeypatch.setattr(search, "search", lambda q, **k: pages or [])
    rules = [("Rank the candidates", {"steps": ultra_steps}),
             ("didn't go ahead", {"subject": "Still thinking about it?", "body": "Hi Hannah, I hope the clinic is doing well! Is the website project still on your mind? Happy to jump on a quick call. Alex"})]
    if prospect_reply:
        rules.append(("plausibly need", prospect_reply))
    return fake(rules)


def test_no_gap_no_plan(fake, monkeypatch):
    _world(monkeypatch, fake, [])
    b = store.read_json("money.json", {})
    b["balance"] = 9000
    store.write_json("money.json", b)
    assert rescue.plan() is None


def test_plan_uses_only_real_candidates_and_drafts_reengagement_for_yes(fake, monkeypatch):
    _world(monkeypatch, fake, [])
    ids = [c["id"] for c in rescue.candidates()]
    assert "invoice:118" in ids and any(i.startswith("revive:") for i in ids)
    hannah = next(i for i in ids if i.startswith("revive:") and "h001" in i)
    _world(monkeypatch, fake, [{"id": "invoice:118", "action": "Call Priya", "why": "fastest"},
                               {"id": hannah, "action": "Check in with Hannah", "why": "warm"},
                               {"id": "made-up:1", "action": "Sell a course", "why": "x"}])
    out = rescue.plan()
    assert [s["id"] for s in out["steps"]] == ["invoice:118", hannah]
    assert out["closes_gap_at"] == "invoice:118"
    assert any("Hannah" in a["summary"] for a in approvals.pending())


def test_prospect_must_be_named_on_the_page_it_cites(fake, monkeypatch):
    page = {"id": "web:p1", "title": "New openings", "url": "https://news.example/p",
            "content": "Rose City Ramen opens its first shop on Alberta Street next month, owner says.", "published": ""}
    reply = {"prospects": [
        {"business": "Rose City Ramen", "why": "new shop", "source": "web:p1", "quote": "Rose City Ramen opens its first shop", "opener": "Congrats on the opening!"},
        {"business": "Hood Bakery", "why": "invented", "source": "web:p1", "quote": "opens its first shop on Alberta Street", "opener": "Hi"}]}
    _world(monkeypatch, fake, [], prospect_reply=reply, pages=[page])
    names = [p["business"] for p in rescue.find_prospects()]
    assert names == ["Rose City Ramen"]
