from datetime import date, timedelta

from kept import intake, ledger, schedule
from kept.seed import seed


def _m(body, frm="Jo Rivera <jo@example.com>"):
    return {"id": "you:t1", "from": frm, "subject": "Kitchen", "date": date.today().isoformat(), "body": body}


def test_visit_slots_skip_sundays_and_taken_times():
    seed(force=True)
    slots = schedule.free_slots(3)
    assert len(slots) == 3 and all(date.fromisoformat(s["date"]).weekday() != 6 for s in slots)
    taken = {(e["date"], e.get("time")) for e in schedule.load()["events"] if e.get("time")}
    assert not any((s["date"], s["time"]) in taken for s in slots)


def test_small_repair_is_priced_now_by_code_with_the_minimum(fake):
    seed(force=True)
    fake([("say what job it is", {"job": "small_repair", "what": "loose hinge", "repair_hours": 0.5})])
    plan = intake.assess(_m("A cabinet door hangs from one hinge, can you fix it?"))
    assert plan["price"] == 170 and plan["hours"] == 2 and len(plan["slots"]) == 3  # times for the repair, no measuring
    rules, allowed, must = intake.reply_rules(plan)
    assert allowed == {170} and "170" in must and "SLOTS" in must and "matched" in rules and "2-hour minimum" in rules


def test_new_fronts_need_a_visit_and_the_pick_is_booked_by_code(fake):
    seed(force=True)
    fake([("say what job it is", {"job": "fronts", "what": "new fronts", "picked_time": ""})])
    plan = intake.assess(_m("We'd like new doors on our old cabinets."))
    assert plan["from_price"] == 4500 and len(plan["slots"]) == 3
    s = plan["slots"][1]
    day = s["label"].split(",")[0]
    fake([("say what job it is", {"job": "fronts", "what": "new fronts", "picked_time": f"{day} at {schedule.clock(s['time'])}"})])
    plan2 = intake.assess(_m(f"{day} at {schedule.clock(s['time'])} works for us!"))
    assert plan2["booked_label"] == s["label"]
    assert any(r["text"].startswith("Measuring visit at Jo's kitchen") for r in ledger.items("open"))
    assert s["date"] in [e["date"] for e in schedule.upcoming() if e.get("who") == "Jo Rivera"]


def test_estimate_comes_from_sizes_and_the_price_guide_and_a_no_gets_a_payment_plan(fake):
    seed(force=True)
    photo = {"shows": "a 1990s kitchen", "scope": "full_kitchen",
             "rough_sizes": {"cabinet_run_ft": 12, "countertop_sqft": 25, "backsplash_sqft": 30}}
    fake([("say what job it is", {"job": "full_kitchen", "what": "new kitchen", "sizes": {}, "material": ""})])
    plan = intake.assess(_m("We'd like a whole new kitchen, photo attached."), photo)
    est = plan["estimate"]
    assert est["mid"] == 12 * 1100 + 25 * 95 + 30 * 35 + 1200 + 600 and est["sizes_from"].startswith("your photo")
    rules, allowed, must = intake.reply_rules(plan)
    assert est["low"] in allowed and "PRELIMINARY" in rules
    fake([("say what job it is", {"job": "full_kitchen", "what": "too expensive", "price_objection": True})])
    plan2 = intake.assess(_m("That's way more than we can afford right now."))
    pp = plan2["payment_plan"]
    assert pp["deposit"] == round(est["mid"] * 0.3 / 10) * 10 and pp["months"] == 12
    assert pp["deposit"] + pp["monthly"] * 12 >= est["mid"]
    rules2, allowed2, must2 = intake.reply_rules(plan2)
    assert pp["monthly"] in allowed2 and "payment plan" in rules2


def test_their_own_numbers_beat_the_photo(fake):
    seed(force=True)
    photo = {"shows": "kitchen", "scope": "refresh", "rough_sizes": {"doors_and_drawers": 10}}
    fake([("say what job it is", {"job": "fronts", "what": "new fronts", "sizes": {"doors_and_drawers": 18}, "material": "solid wood"})])
    plan = intake.assess(_m("New solid wood doors please, we have 18 doors and drawers."), photo)
    assert plan["estimate"]["mid"] == 18 * 380 and plan["estimate"]["sizes_from"] == "your numbers"


def test_a_repair_for_a_client_under_contract_is_not_priced_separately(fake):
    seed(force=True)
    fake([("say what job it is", {"job": "small_repair", "what": "pantry door", "repair_hours": 1})])
    plan = intake.assess(_m("The pantry door doesn't close.", frm="Maria Lopez <maria@lopezhome.example>"), has_contract=True)
    assert plan.get("on_site") and "price" not in plan
    rules, allowed, must = intake.reply_rules(plan)
    assert not allowed and "don't put a price" in rules


def test_sizes_written_as_words_dont_crash_and_counts_add_up():
    from kept import estimate
    seed(force=True)
    assert estimate._num("8 upper doors, 6 lower doors, 4 drawers", add_up=True) == 18
    assert estimate._num("about 12 ft") == 12
    assert estimate._num("not sure") is None
    est = estimate.preliminary("fronts", {"doors_and_drawers": "8 upper doors, 6 lower doors, 4 drawers"})
    assert est["mid"] == 18 * 250
