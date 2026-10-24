"""Talking to Kept: code, not a model, hears the Yes; anything unclear sends nothing."""
import pytest

from kept import approvals, voice
from kept.tools import mail  # noqa: F401  registers send_email


@pytest.mark.parametrize("said,want", [
    ("Yes", "yes"), ("yeah send it", "yes"), ("Sure, go ahead.", "yes"), ("okay do it", "yes"),
    ("No", "no"), ("hold on", "no"), ("don't", "no"), ("wait", "no"),
    ("Don't send it", "unclear"), ("yes but change the time", "unclear"), ("no, send it", "unclear"),
    ("", "unclear"), ("hmm", "unclear"), ("not okay", "unclear"), ("I'm not sure, send it", "unclear"),
])
def test_yes_and_no_are_read_from_the_words(said, want):
    assert voice.verdict(said) == want


def _waiting():
    return approvals.propose("send_email", {"to": "maria@lopezhome.example", "subject": "s", "body": "Hi Maria"},
                             summary="Reply to Maria", why="she asked")


def test_a_spoken_yes_sends_the_one_that_was_read_out(fake):
    a = _waiting()
    out = voice.handle("yes, send it", a["id"])
    assert out["decided"] == "yes" and approvals.get(a["id"])["status"] == "done"
    assert approvals.get(a["id"])["by"] == "owner (voice)"


@pytest.mark.parametrize("said", ["yes but change the time", "don't send it", "mm", "send it to Jo instead"])
def test_an_unclear_answer_sends_nothing(fake, said):
    a = _waiting()
    out = voice.handle(said, a["id"])
    assert approvals.get(a["id"])["status"] == "pending"
    assert "decided" not in out


def test_a_spoken_no_only_holds_the_draft(fake):
    a = _waiting()
    out = voice.handle("no", a["id"])
    assert out["decided"] == "held" and approvals.get(a["id"])["status"] == "pending"


def test_a_yes_without_anything_read_out_sends_nothing(fake):
    a = _waiting()
    fake([("Question:", {"answer": "x", "evidence": []})])
    voice.handle("yes", None)
    assert approvals.get(a["id"])["status"] == "pending"


def test_whats_waiting_reads_the_draft_and_asks(fake):
    a = _waiting()
    out = voice.handle("what's waiting?")
    assert out["pending_id"] == a["id"] and "Hi Maria" in out["say"] and out["say"].endswith("Shall I send it?")


def test_a_question_is_answered_only_when_its_quotes_check_out(fake):
    from kept import ledger
    row = ledger.add("Send Maria the revised quote", who="Maria Lopez", due="2026-10-23")
    fake([("Question:", {"answer": "You owe Maria the revised quote.",
                         "evidence": [{"source": f"ledger:{row['id']}", "quote": "Send Maria the revised quote"}]})])
    assert voice.handle("What do I owe Maria?")["say"] == "You owe Maria the revised quote."
    fake([("Question:", {"answer": "You owe Maria a logo.",
                         "evidence": [{"source": f"ledger:{row['id']}", "quote": "design a logo"}]})])
    assert "won't guess" in voice.handle("What do I owe Maria?")["say"]


def test_a_question_while_a_draft_waits_does_not_send_it(fake):
    a = _waiting()
    fake([("Question:", {"answer": "x", "evidence": []})])
    voice.handle("Is it okay to send?", a["id"])
    assert approvals.get(a["id"])["status"] == "pending"


def test_whats_waiting_reads_the_one_on_screen_first(fake):
    first = _waiting()
    shown = approvals.propose("send_email", {"to": "jo@riverahome.example", "subject": "s", "body": "Hi Jo"},
                              summary="Reply to Jo", why="new lead")
    assert voice.handle("what's waiting?", shown["id"])["pending_id"] == shown["id"]
    assert voice.handle("next one", shown["id"])["pending_id"] == first["id"]


def test_dates_and_numbers_are_said_the_way_a_person_says_them():
    assert voice.speakable("Cash will be short $116 on 2026-11-01. Invoice #118.") == \
        "Cash will be short $116 on Sunday, November 1. Invoice number 118."
