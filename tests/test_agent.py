import json
from datetime import date, timedelta

from kept import agent, approvals, ledger, store

TODAY = date.today()


def _inbox(rows):
    (store.data_dir() / "inbox.json").write_text(json.dumps(rows))


MAIL = {"id": "mail:1", "from": "Maria Lopez <maria@bakery.example>", "subject": "Quote for the website",
        "date": "", "body": "Hi! Thanks for the call. You said you'd send the revised quote by "
                            f"{(TODAY - timedelta(days=1)).isoformat()}. Looking forward to it. Maria"}


def test_triage_extracts_only_grounded_commitments(fake):
    _inbox([MAIL])
    fake([
        ("Classify this email", {"kind": "client", "needs_reply": True, "one_line": "Maria waits for quote"}),
        ("List promises", {"items": [
            {"text": "Send Maria the revised quote", "who": "Maria Lopez", "due": (TODAY - timedelta(days=1)).isoformat(),
             "quote": "you'd send the revised quote by"},
            {"text": "Build her a logo", "who": "Maria", "due": None, "quote": "and you also promised a free logo"},
        ]}),
    ])
    rep = agent.triage_inbox()
    texts = [r["text"] for r in ledger.items("open")]
    assert texts == ["Send Maria the revised quote"]          # the invented logo promise is dropped
    held = store.read_json("abstained.json", [])
    assert any("not in source" in p for h in held for p in h["problems"])
    assert agent.triage_inbox()["new"] == 0                  # mail is not re-read


def test_follow_up_drafts_then_waits_for_yes(fake):
    _inbox([MAIL])
    ledger.add("Send Maria the revised quote", who="Maria Lopez", due=(TODAY - timedelta(days=1)).isoformat(),
               source="mail:1")
    fake([("Write a short, warm", {"subject": "Your revised quote", "body": "Hi Maria, here is where the quote stands..."})])
    asked = agent.follow_ups()
    assert len(asked) == 1 and asked[0]["status"] == "pending"
    assert list((store.data_dir() / "outbox").iterdir()) == []   # nothing sent without Yes
    approvals.decide(asked[0]["id"], True)
    assert len(list((store.data_dir() / "outbox").iterdir())) == 1


def test_follow_up_abstains_on_template_hole(fake):
    _inbox([MAIL])
    ledger.add("Send Maria the revised quote", who="Maria Lopez", due=TODAY.isoformat(), source="mail:1")
    fake([("Write a short, warm", {"subject": "Quote", "body": "Hi [Name], quote soon."})])
    assert agent.follow_ups() == []
    assert approvals.pending() == []


def test_brief_never_drops_an_overdue_promise(fake):
    row = ledger.add("Pay the accountant", who="Sam", due=(TODAY - timedelta(days=3)).isoformat())
    fake([("morning brief", {"headline": "Quiet day", "lines": [{"ref": None, "text": "Coffee"}], "plan": ["a"]})])
    b = agent.morning_brief()
    assert b["lines"][0]["ref"] == row["id"] and b["lines"][0]["added_by"] == "rule"


def test_brief_strips_references_to_things_that_dont_exist(fake):
    fake([("morning brief", {"headline": "h", "lines": [{"ref": "zzzz", "text": "ghost task"}], "plan": []})])
    b = agent.morning_brief()
    assert all(ln["ref"] != "zzzz" for ln in b["lines"])


def test_overload_uses_ultra_and_still_needs_yes(fake):
    rows = [ledger.add(f"Deliver item {i}", who=f"client{i}@x.example", due=(TODAY + timedelta(days=1)).isoformat())
            for i in range(3)]
    fb = fake([("Pick the ONE", lambda p: {"move_id": rows[1]["id"], "new_due": (TODAY + timedelta(days=6)).isoformat(),
                                           "reason": "smallest impact", "to": "client1@x.example",
                                           "subject": "Moving the date", "body": "Hi, could we move this to next week?"})])
    req = agent.weigh_overload()
    assert req and req["status"] == "pending"
    assert "Ultra" in fb.calls[-1][0]


def test_watch_keeps_only_quoted_facts(fake, monkeypatch):
    from kept.tools import search
    page = "Stripe announced that card fees for small merchants rise to 3.1 percent from January 1."
    monkeypatch.setattr(search, "search", lambda q, **k: [
        {"id": "web:aa", "title": "Stripe fees", "url": "https://news.example/stripe", "content": page, "published": ""}])
    fake([("The owner follows this topic", {"claims": [
        {"text": "Stripe fees rise in January", "source": "web:aa", "quote": "card fees for small merchants rise to 3.1 percent"},
        {"text": "Stripe is shutting down", "source": "web:aa", "quote": "Stripe will close all accounts next month"},
    ]})])
    out = agent.watch_topics(["Stripe fees for small businesses"])
    assert [c["text"] for c in out["claims"]] == ["Stripe fees rise in January"]
    assert out["dropped"] == 1


def test_memory_answer_is_verified_only_with_real_quotes(fake):
    from kept import memory_qa
    row = ledger.add("Send Maria the revised quote", who="Maria Lopez", due="2026-10-23")
    fake([("Question:", {"answer": "You owe Maria the revised quote.",
                         "evidence": [{"source": f"ledger:{row['id']}", "quote": "Send Maria the revised quote"}]})])
    assert memory_qa.ask("What do I owe Maria?")["verified"] is True
    fake([("Question:", {"answer": "You owe Maria a logo.",
                         "evidence": [{"source": f"ledger:{row['id']}", "quote": "design a new logo for Maria"}]})])
    assert memory_qa.ask("What do I owe Maria?")["verified"] is False
