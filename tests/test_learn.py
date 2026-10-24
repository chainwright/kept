from datetime import date, timedelta

import pytest

from kept import agent, approvals, learn
from tests.test_calibration import _closed


@pytest.fixture
def skills_dir(tmp_path, monkeypatch):
    for name in ("follow_up", "extract", "brief"):
        (tmp_path / f"{name}.md").write_text(f"# Skill: {name}\n")
    monkeypatch.setattr(agent, "SKILLS", tmp_path)
    monkeypatch.setattr(learn, "SKILLS", tmp_path)
    return tmp_path


def _history():
    base = date(2026, 8, 28)  # a Friday
    for i, late in enumerate([2, 3, 2, 0, 3]):   # quotes to new leads, due Fridays
        due = base + timedelta(weeks=i)
        _closed(f"Send the quote to lead {i}", due, due + timedelta(days=late), who=f"Lead {i}")
    for i in range(4):                            # fixes are on time
        due = base + timedelta(weeks=i, days=2)
        _closed(f"Fix the bug {i}", due, due, who="Jordan")


def test_rule_with_real_pattern_waits_for_yes_then_changes_the_skill(fake, skills_dir):
    _history()
    fake([("Find at most two patterns", {"rules": [{"rule": "When quoting a new lead, add two working days to the date you'd normally give.",
                                                    "skill": "follow_up", "explain": "Quotes slip",
                                                    "pattern": {"kind": "quote"}}]})])
    [req] = learn.propose_rules()
    assert "4 of these 5" in req["why"]
    assert "Learned from" not in (skills_dir / "follow_up.md").read_text()   # nothing changed yet
    approvals.decide(req["id"], True)
    assert "add two working days" in (skills_dir / "follow_up.md").read_text()
    assert "add two working days" in agent._msgs("x", "follow_up")[0]["content"]  # used from now on


def test_rule_whose_evidence_shows_no_pattern_is_held_back(fake, skills_dir):
    _history()
    fake([("Find at most two patterns", {"rules": [{"rule": "Add a day to every bug fix.", "skill": "follow_up",
                                                    "explain": "fixes slip", "pattern": {"kind": "fix"}}]})])
    assert learn.propose_rules() == []
    assert approvals.pending() == []


def test_rule_cannot_cherry_pick_its_evidence(fake, skills_dir):
    _history()
    # 4 of the 5 quotes were late; the on-time one is counted whether Ultra likes it or not
    fake([("Find at most two patterns", {"rules": [{"rule": "Add two days to quotes.", "skill": "follow_up",
                                                    "explain": "x", "pattern": {"kind": "quote"}}]})])
    [req] = learn.propose_rules()
    assert "4 of these 5" in req["why"]


def test_pattern_matching_nothing_is_held_back(fake, skills_dir):
    _history()
    fake([("Find at most two patterns", {"rules": [{"rule": "Add a day to invoices.", "skill": "follow_up",
                                                    "explain": "x", "pattern": {"kind": "pay"}}]})])
    assert learn.propose_rules() == []


def test_rule_that_promises_earlier_for_late_work_is_held_back(fake, skills_dir):
    _history()
    fake([("Find at most two patterns", {"rules": [{"rule": "When promising a quote for Friday, name Wednesday instead.",
                                                    "skill": "follow_up", "explain": "x",
                                                    "pattern": {"kind": "quote", "due_weekday": "due Friday"}}]})])
    assert learn.propose_rules() == []


def test_pattern_values_are_normalised():
    hist = [{"id": "1", "kind": "quote", "due_weekday": "Friday", "who": "A", "days_late": 2}]
    assert len(learn.matching({"kind": "Quote", "due_weekday": "Fridays"}, hist)) == 1
