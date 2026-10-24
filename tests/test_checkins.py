from kept import approvals, checkins
from kept.seed import seed


def test_only_finished_paid_quiet_clients_get_a_check_in():
    seed(force=True)
    ok, skipped = checkins.candidates()
    names = {c["client"] for c in ok}
    why = {c["client"]: c["why_not"] for c in skipped}
    assert "Ben Carter" in names
    assert why["Priya Shah"] == "has unpaid work"
    assert why["Noah Brooks"].startswith("a bigger past job")


def test_check_in_with_a_discount_or_made_up_price_is_held_back(fake):
    seed(force=True)
    fake([("check-in email", {"subject": "Hi Ben", "body": "Hi Ben, how are the drawers? New cabinets are $3,999 this month only, 20% off! Alex"})])
    out = checkins.propose()
    assert out["asked"] == [] and not [a for a in approvals.pending() if a["args"]["to"] == "ben@carterhome.example"]


def test_good_check_in_waits_for_yes(fake):
    seed(force=True)
    fake([("check-in email", {"subject": "How are the drawers?", "body": "Hi Ben, it's been about six weeks since I fixed the drawers and hinges. Are they still running smoothly? If you're still thinking about new cabinet fronts, those start from $4,500. Alex"})])
    out = checkins.propose()
    assert len(out["asked"]) >= 1
    a = approvals.get(out["asked"][0])
    assert a["status"] == "pending" and a["args"]["to"] == "ben@carterhome.example"
