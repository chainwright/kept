import json
from datetime import date

from kept import snapshot, store
from kept.seed import seed


def test_shift_keeps_weekdays_and_formats():
    rec = date(2026, 10, 24)
    days = snapshot.weeks_shift(rec, date(2026, 12, 3))
    assert days == 35  # whole weeks only, never past today
    t = "due 2026-10-30; by Friday, Oct 30; on October 30, 2026; paid Nov. 2; Jan 4 next year"
    out = snapshot.shift_text(t, days, rec)
    assert "2026-12-04" in out and "Dec 4" in out and "December 4, 2026" in out
    assert "Dec. 7" in out and "Feb 8" in out and "Friday" in out
    assert date(2026, 12, 4).weekday() == date(2026, 10, 30).weekday()
    assert snapshot.shift_text(t, 0, rec) == t


def test_restore_moves_files_and_dates(monkeypatch, tmp_path):
    seed(force=True)
    store.write_json("brief.json", {"lines": [{"text": "Quote for Maria due 2026-10-30"}]})
    (store.data_dir() / "journal" / "2026-10-23.md").write_text("# 2026-10-23\n")
    monkeypatch.setattr(snapshot, "SNAP", tmp_path / "snap")
    snapshot.save(recorded_on=date(2026, 10, 24))
    info = snapshot.restore(today=date(2026, 11, 9))
    assert info["shifted_days"] == 14 and info["shown_as"] == "2026-11-07"
    assert "2026-11-13" in json.dumps(store.read_json("brief.json", {}))
    assert (store.data_dir() / "journal" / "2026-11-06.md").exists()
    assert snapshot.meta()["recorded_on"] == "2026-10-24"
    seed(force=True)
    assert snapshot.meta() is None
