"""Demo data: one week in the life of Alex, who runs a one-person web studio.
All people, companies and addresses below are made up (example.com / .example)."""
from __future__ import annotations

import json
import shutil
from datetime import date, timedelta

from .store import data_dir, write_json


def _d(days: int) -> str:
    return (date.today() + timedelta(days=days)).isoformat()


def inbox() -> list[dict]:
    return [
        {"id": "demo:1", "from": "Maria Lopez <maria@sunrisebakery.example>", "date": _d(-3),
         "subject": "Re: website refresh",
         "body": f"Hi Alex,\n\nThanks for the call on Monday. You said you'd send the revised quote with the "
                 f"online ordering page by {_d(-1)}, so I can show it to my partner over the weekend.\n\n"
                 "Also, could the menu page show prices in both sizes?\n\nMaria"},
        {"id": "demo:2", "from": "Dev Patel <dev@greenleaflandscaping.example>", "date": _d(-1),
         "subject": "Website for a landscaping company",
         "body": "Hello, I found your portfolio through a friend. We need a 5-page site with a gallery and "
                 "a quote request form. Could you send me your rates and a rough timeline by Friday? "
                 "We'd like to launch before spring.\n\nThanks,\nDev"},
        {"id": "demo:3", "from": "Billing <billing@hostingco.example>", "date": _d(-2),
         "subject": "Invoice #4412 is due",
         "body": f"Your invoice #4412 for $36.00 (Business hosting, monthly) is due on {_d(2)}. "
                 "To avoid interruption, please pay before the due date."},
        {"id": "demo:4", "from": "Design Weekly <news@designweekly.example>", "date": _d(-1),
         "subject": "10 fonts you'll love this autumn",
         "body": "Our editors picked ten typefaces for your next project. Plus: a giveaway!"},
        {"id": "demo:5", "from": "Sam Okafor <sam@okaforcpa.example>", "date": _d(-1),
         "subject": "Q3 receipts",
         "body": f"Hi Alex, friendly reminder: please send me your Q3 receipts before {_d(1)} so I can "
                 "file on time. A zip or a shared folder is fine.\n\nSam"},
        {"id": "demo:6", "from": "Jordan Kim <jordan@kimyoga.example>", "date": _d(0),
         "subject": "Launch call + contact form",
         "body": f"Hey Alex! Can we push our launch call to {_d(2)}? Something came up on my side. "
                 "Also, last week you mentioned you'd fix the contact form bug this week. Is that still "
                 "the plan? People told me the form says 'sent' but I never get the message.\n\nJordan"},
    ]


NOTES = """# About the owner
Alex Rivera runs a one-person web design studio. Clients are local small businesses.
Prefers short, friendly emails. Signs as "Alex". Works 9:00-17:00, no meetings on Fridays.

## Watch
- Stripe fees for small businesses
- Google search changes for local businesses
- Squarespace and Wix pricing changes
"""


def seed(force: bool = False) -> None:
    d = data_dir()
    if (d / "inbox.json").exists() and not force:
        return
    if force:
        for p in d.iterdir():
            shutil.rmtree(p) if p.is_dir() else p.unlink()
        d = data_dir()
    (d / "inbox.json").write_text(json.dumps(inbox(), indent=1))
    (d / "notes.md").write_text(NOTES)
    y = (date.today() - timedelta(days=1)).isoformat()
    write_json("ledger.json", [
        {"id": "a1c0de01", "text": "Send Jordan the new homepage photos", "who": "Jordan Kim", "due": y,
         "source": "", "origin": "owner", "status": "done", "created": f"{_d(-4)}T16:00:00+00:00",
         "closed": f"{y}T17:40:00+00:00", "note": "Shared the folder with 12 photos; Jordan replied thanks",
         "history": []},
        {"id": "a1c0de02", "text": "Renew the domain for Sunrise Bakery", "who": "Maria Lopez", "due": _d(3),
         "source": "", "origin": "owner", "status": "open", "created": f"{_d(-5)}T10:00:00+00:00",
         "history": []},
    ])
    (d / "journal" / f"{y}.md").write_text(
        f"# {y}\n\n- 07:30 Morning brief: two promises due, one overdue\n"
        "- 17:40 Closed a1c0de01 as done: Shared the folder with 12 photos; Jordan replied thanks\n")


if __name__ == "__main__":
    seed(force=True)
    print("demo data written to", data_dir())
