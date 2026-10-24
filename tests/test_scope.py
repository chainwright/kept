import json

from kept import approvals, scope, store

AGREEMENT = """# Website refresh for Sunrise Bakery
Price: $2,400, paid in two parts.
Included:
- Four pages: Home, Menu, About, Contact.
- Two rounds of revisions on the design.
Not included: online ordering, a blog, photography.
"""
MAIL = {"id": "mail:8", "from": "Maria Lopez <maria@bakery.example>", "subject": "Two small things", "date": "",
        "body": "Hi Alex! Could you add a small blog page where we post seasonal specials? "
                "And could the logo be a bit bigger on the home page? Thanks, Maria"}


def _setup():
    d = store.data_dir() / "contracts"
    d.mkdir(exist_ok=True)
    (d / "maria@bakery.example.md").write_text(AGREEMENT)
    (store.data_dir() / "notes.md").write_text("# About\nHourly rate: $85\n")


VERDICT = {"requests": [
    {"request": "Add a blog page", "email_quote": "add a small blog page where we post seasonal specials",
     "verdict": "out_of_scope", "agreement_quote": "Not included: online ordering, a blog, photography.",
     "reason": "blog excluded", "hours_low": 3, "hours_high": 5},
    {"request": "Make the logo bigger", "email_quote": "could the logo be a bit bigger on the home page",
     "verdict": "in_scope", "agreement_quote": "Two rounds of revisions on the design.", "reason": "revision",
     "hours_low": 0, "hours_high": 0}]}


def test_out_of_scope_request_is_priced_by_code_and_waits_for_yes(fake):
    _setup()
    fake([("signed agreement", VERDICT),
          ("Confirm the covered items", {"subject": "Logo + blog", "body": "Hi Maria,\nHappy to make the logo bigger, that's part of our revisions. The blog page wasn't in our agreement; I can add it for $340. Want me to go ahead?\nAlex"})])
    res = scope.review(MAIL)
    blog = [r for r in res["requests"] if r["verdict"] == "out_of_scope"][0]
    assert blog["price"] == 340            # 4h midpoint * $85 = 340, rounded up to $5
    assert res["proposal"]["status"] == "pending" and "$340" in res["proposal"]["summary"]


def test_verdict_quoting_words_not_in_the_agreement_is_held_back(fake):
    _setup()
    bad = json.loads(json.dumps(VERDICT))
    bad["requests"][0]["agreement_quote"] = "Blogs cost extra at $500 per page."
    fake([("signed agreement", bad)])
    res = scope.review(MAIL)
    assert all(r["request"] != "Add a blog page" for r in res["requests"])
    assert res["proposal"] is None


def test_email_with_a_price_code_didnt_compute_is_held_back(fake):
    _setup()
    fake([("signed agreement", VERDICT),
          ("Confirm the covered items", {"subject": "x", "body": "Hi Maria,\nThe blog is $340, and a gallery would be $900.\nAlex"})])
    assert scope.review(MAIL)["proposal"] is None
    assert approvals.pending() == []


def test_no_agreement_no_scope_check(fake):
    assert scope.review({**MAIL, "from": "Stranger <who@nowhere.example>"}) is None


def test_two_reads_that_disagree_become_unclear_and_ask_for_nothing(fake):
    _setup()
    calls = {"n": 0}

    def judge(_):
        calls["n"] += 1
        v = json.loads(json.dumps(VERDICT))
        if calls["n"] == 2:   # the second read thinks the blog is covered
            v["requests"][0]["verdict"] = "in_scope"
            v["requests"][0]["agreement_quote"] = "Four pages: Home, Menu, About, Contact."
        return v
    fake([("signed agreement", judge)])
    res = scope.review(MAIL)
    blog = [r for r in res["requests"] if r["request"] == "Add a blog page"][0]
    assert blog["verdict"] == "unclear" and res["proposal"] is None


def test_request_the_owner_already_promised_is_not_sold_again(fake):
    _setup()
    from kept import ledger
    ledger.add("Send Maria a quote for the blog page", who="Maria Lopez", source="mail:8")
    fake([("signed agreement", VERDICT)])
    res = scope.review(MAIL)
    blog = [r for r in res["requests"] if r["request"] == "Add a blog page"][0]
    assert blog["verdict"] == "already_promised" and res["proposal"] is None
