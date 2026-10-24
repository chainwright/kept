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
        ("Find two kinds", {"mine": [
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
    rows = [ledger.add(f"Deliver item {i}", who=f"Client{i} Smith", contact=f"client{i}@x.example",
                       due=(TODAY + timedelta(days=1)).isoformat()) for i in range(3)]
    fb = fake([("Pick the ONE", lambda p: {"move_id": rows[1]["id"], "new_due": (TODAY + timedelta(days=6)).isoformat(),
                                           "reason": "smallest impact", "to": "made-up@example.com",
                                           "subject": "Moving the date", "body": "Hi Client1, could we move this to next week?"})])
    req = agent.weigh_overload()
    assert req and req["status"] == "pending"
    assert "Ultra" in fb.calls[-1][0]
    assert req["args"]["to"] == "client1@x.example"     # never the address the model typed


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


# ---- regressions from the first live run on Nemotron (Oct 24) ----
def test_extracted_promise_is_owed_to_the_sender_not_the_owner(fake):
    _inbox([MAIL])
    fake([("Classify this email", {"kind": "client", "needs_reply": True, "one_line": "x"}),
          ("Find two kinds", {"mine": [{"text": "send the revised quote", "who": "Alex", "due": None,
                                      "quote": "you'd send the revised quote by"}]})])
    agent.triage_inbox()
    row = ledger.items("open")[0]
    assert row["who"] == "Maria Lopez" and row["contact"] == "maria@bakery.example"
    assert row["text"] == "Send the revised quote"


def test_follow_up_that_greets_the_owner_is_held_back(fake):
    _inbox([MAIL])
    ledger.add("Send Maria the revised quote", who="Maria Lopez", contact="maria@bakery.example",
               due=TODAY.isoformat(), source="mail:1")
    fake([("Write a short, warm", {"subject": "Quote", "body": "Hi Alex,\nThe quote is coming today. Maria asked about sizes.\nAlex"})])
    assert agent.follow_ups() == []
    probs = store.read_json("abstained.json", [])[-1]["problems"]
    assert any("addresses Alex" in p for p in probs)


def test_follow_up_promising_a_past_date_is_held_back(fake):
    _inbox([MAIL])
    ledger.add("Send Maria the revised quote", who="Maria Lopez", contact="maria@bakery.example",
               due=TODAY.isoformat(), source="mail:1")
    past = (TODAY - timedelta(days=1)).isoformat()
    fake([("Write a short, warm", {"subject": "Quote", "body": f"Hi Maria, I'm on track to send it by {past}. Alex"})])
    assert agent.follow_ups() == []
    assert any("already passed" in p for p in store.read_json("abstained.json", [])[-1]["problems"])


def test_bracketed_source_ids_still_count_as_the_same_source():
    from kept.validators import grounded
    assert grounded([{"source": "[web:aa]", "quote": "card fees for small merchants rise"}],
                    {"web:aa": "Stripe said card fees for small merchants rise in January."})


def test_overload_skips_promises_that_already_have_a_message_waiting(fake):
    rows = [ledger.add(f"Deliver item {i}", who=f"Client{i} Smith", contact=f"client{i}@x.example",
                       due=(TODAY + timedelta(days=1)).isoformat()) for i in range(3)]
    approvals.propose("send_email", {"to": "client0@x.example", "subject": "s", "body": "b"},
                      summary="x", why="y", ledger_id=rows[0]["id"])
    fb = fake([("Pick the ONE", {"move_id": rows[0]["id"], "new_due": (TODAY + timedelta(days=6)).isoformat(),
                                 "reason": "r", "subject": "s", "body": "Hi Client0, can we move it?"})])
    assert agent.weigh_overload() is None        # Ultra picked the busy one; code refuses it
    assert rows[0]["id"] not in fb.calls[-1][1]  # and it was never offered as a choice


def test_promises_owed_to_the_owner_are_tracked_and_nudged_only_when_late(fake):
    pay = {"id": "mail:9", "from": "Priya Shah <priya@studio.example>", "subject": "Invoice 118", "date": "",
           "body": f"Hi Alex, sorry for the wait. We'll pay invoice #118 by {(TODAY - timedelta(days=3)).isoformat()}. Priya"}
    _inbox([pay])
    fake([("Classify this email", {"kind": "client", "needs_reply": False, "one_line": "payment promise"}),
          ("Find two kinds", {"mine": [], "theirs": [{"text": "Priya pays invoice #118",
                                                       "due": (TODAY - timedelta(days=3)).isoformat(),
                                                       "quote": "We'll pay invoice #118 by"}]}),
          ("Write a short, warm", {"subject": "Invoice #118", "body": "Hi Priya, just checking when invoice #118 might go through? Thanks, Alex"})])
    agent.triage_inbox()
    row = ledger.open_sorted(which="owed_to_me")[0]
    assert row["who"] == "Priya Shah" and row["contact"] == "priya@studio.example"
    asked = agent.follow_ups()
    assert len(asked) == 1 and "Priya Shah promised" in asked[0]["why"]


def test_promise_copied_in_the_clients_voice_is_put_in_the_owners_ledger_voice(fake):
    lead = {"id": "mail:5", "from": "Dev Patel <dev@x.example>", "subject": "Site", "date": "",
            "body": "Could you send me your rates and a rough timeline by Friday?"}
    _inbox([lead])
    fake([("Classify this email", {"kind": "lead", "needs_reply": True, "one_line": "x"}),
          ("Find two kinds", {"mine": [{"text": "send me your rates and a rough timeline", "due": None,
                                        "quote": "send me your rates and a rough timeline"}], "theirs": []})])
    agent.triage_inbox()
    assert ledger.items("open")[0]["text"] == "Send Dev your rates and a rough timeline"
