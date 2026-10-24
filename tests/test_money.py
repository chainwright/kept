from datetime import date, timedelta

from kept import approvals, money, store

T = date(2026, 10, 24)


def _book():
    store.write_json("money.json", {
        "balance": 1240.0, "as_of": T.isoformat(),
        "invoices": [
            {"number": "109", "client": "Priya Shah", "contact": "priya@x.example", "amount": 600, "issued": "2026-08-01", "due": "2026-08-15", "paid_on": "2026-08-27"},
            {"number": "113", "client": "Priya Shah", "contact": "priya@x.example", "amount": 700, "issued": "2026-09-01", "due": "2026-09-15", "paid_on": "2026-09-28"},
            {"number": "118", "client": "Priya Shah", "contact": "priya@x.example", "amount": 850, "issued": "2026-10-08", "due": "2026-10-22", "paid_on": None},
            {"number": "121", "client": "Maria Lopez", "contact": "maria@x.example", "amount": 1200, "issued": "2026-10-20", "due": "2026-11-10", "paid_on": None},
        ],
        "bills": [
            {"payee": "Hosting", "amount": 36, "due": "2026-10-26", "recurring": "monthly"},
            {"payee": "Insurance", "amount": 420, "due": "2026-10-30"},
            {"payee": "Studio rent", "amount": 900, "due": "2026-11-01", "recurring": "monthly"},
        ]})


def test_client_habit_moves_the_expected_payment():
    _book()
    assert money.payment_habit("Priya Shah")["typical_days_late"] == 12
    inv = money.load()["invoices"][2]
    assert money.expected_payment(inv, T, money.load()) == date(2026, 11, 3)


def test_forecast_finds_the_shortfall_and_the_invoice_that_fixes_it():
    _book()
    f = money.forecast(30, today=T)
    assert f["short"] == {"date": "2026-11-01", "gap": 116.0, "because": "Studio rent"}
    assert f["fix"][0]["invoice"] == "118"


def test_ladder_steps():
    assert money.step_for(0) is None
    assert money.step_for(2)[0] == "friendly" and money.step_for(10)[0] == "firm" and money.step_for(30)[0] == "final"


def test_reminder_with_wrong_amount_or_threat_is_held_back(fake):
    _book()
    fake([("about invoice #118", {"subject": "Invoice 118", "body": "Hi Priya, quick nudge on invoice #118 for $580. Thanks, Alex"})])
    assert money.chase(today=T) == []
    fake([("about invoice #118", {"subject": "Invoice 118", "body": "Hi Priya, invoice #118 for $850 is late; a late fee applies. Alex"})])
    assert money.chase(today=T) == []
    probs = [p for h in store.read_json("abstained.json", []) for p in h["problems"]]
    assert any("$850" in p for p in probs) and any("threaten" in p for p in probs)


def test_good_reminder_waits_for_yes_and_sending_records_the_step(fake):
    _book()
    fake([("about invoice #118", {"subject": "Invoice #118", "body": "Hi Priya, just a friendly nudge on invoice #118 for $850. Thanks so much, Alex"})])
    [req] = money.chase(today=T)
    assert req["status"] == "pending" and "usually pays 12 days late" in req["why"]
    approvals.decide(req["id"], True)
    assert money.load()["invoices"][2]["reminders"][0]["step"] == "friendly"
    assert money.chase(today=T) == []      # the same step is not sent twice
