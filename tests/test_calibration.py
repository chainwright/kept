from datetime import date, timedelta

from kept import calibration, ledger, store


def _closed(text, due, done_on, who="Maria"):
    rows = store.read_json("ledger.json", [])
    rows.append({"id": f"h{len(rows)}", "text": text, "who": who, "due": due.isoformat(), "status": "done",
                 "closed": f"{done_on.isoformat()}T17:00:00+00:00", "note": "done", "created": "", "history": []})
    store.write_json("ledger.json", rows)


def test_no_history_no_advice():
    assert calibration.realistic_due("Send the quote to Dev", "2026-11-06") is None


def test_quotes_that_usually_slip_get_a_later_date():
    base = date(2026, 9, 4)
    for i, late in enumerate([2, 3, 2, 0, 2]):
        due = base + timedelta(weeks=i)
        _closed(f"Send the quote to client {i}", due, due + timedelta(days=late))
    adv = calibration.realistic_due("Send Dev the rates and a quote", "2026-11-06")  # a Friday
    assert adv["kind"] == "quote" and adv["kept"] == 1 and adv["total"] == 5
    assert adv["suggested"] == "2026-11-09"   # +2 days lands on Sunday -> next Monday
    assert adv["why"] == "Of your last 5 'quote' promises, 1 was on time; the typical one landed 2 days late."


def test_on_time_history_means_no_nagging():
    base = date(2026, 9, 4)
    for i in range(4):
        due = base + timedelta(weeks=i)
        _closed(f"Fix the bug {i}", due, due)
    assert calibration.realistic_due("Fix the contact form bug", "2026-11-06") is None


def test_report_groups_by_person_and_weekday():
    base = date(2026, 9, 4)  # Friday
    _closed("Send the quote", base, base + timedelta(days=2), who="Dev")
    _closed("Fix the bug", base + timedelta(days=3), base + timedelta(days=3), who="Jordan")
    rep = calibration.as_json()
    assert rep["by_person"]["Dev"]["kept"] == 0 and rep["by_person"]["Jordan"]["kept"] == 1
    assert rep["by_weekday"]["Friday"]["total"] == 1
