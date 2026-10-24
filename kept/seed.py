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
                 f"a quote request form. Could you send me your rates and a rough timeline by {_d(2)}? "
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
        {"id": "demo:7", "from": "Priya Shah <priya@shahdental.example>", "date": _d(-6),
         "subject": "Re: invoice #118",
         "body": f"Hi Alex, thanks for the reminder and sorry for the delay! Our office manager is back on "
                 f"Monday. We'll pay invoice #118 ($850) by {_d(-2)} at the latest.\n\nPriya"},
        {"id": "demo:8", "from": "Maria Lopez <maria@sunrisebakery.example>", "date": _d(0),
         "subject": "Two small things",
         "body": "Hi Alex! While you're on it, could you add a small blog page where we can post our seasonal "
                 "specials? And could the logo be a bit bigger on the home page? It looks tiny on my phone.\n\n"
                 "Thank you!! Maria"},
        {"id": "demo:9", "from": "Noah Brooks <noah@brookscoffee.example>", "date": _d(-1),
         "subject": "We're live!",
         "body": "Alex! The new site went live this morning and we already got two catering inquiries "
                 "through the form. Customers keep telling us how easy the menu is to read on their phones. "
                 "You were great to work with, thank you!\n\nNoah"},
        {"id": "demo:6", "from": "Jordan Kim <jordan@kimyoga.example>", "date": _d(0),
         "subject": "Launch call + contact form",
         "body": f"Hey Alex! Can we push our launch call to {_d(2)}? Something came up on my side. "
                 "Also, last week you mentioned you'd fix the contact form bug this week. Is that still "
                 "the plan? People told me the form says 'sent' but I never get the message.\n\nJordan"},
    ]


NOTES = """# About the owner
Alex Rivera runs a one-person web design studio in Portland, Oregon. Clients are local small
businesses: cafes, bakeries, clinics, studios, shops.
Prefers short, friendly emails. Signs as "Alex". Works 9:00-17:00, no meetings on Fridays.

## Rates
- Hourly rate: $85

## Offers
- Max discount: 15%
- Minimum project price: $900
- One offer per client per 60 days

## Reviews and posts
- Review link: https://g.page/r/alex-rivera-studio/review
- Clients I may name in posts: Brooks Coffee, Sunrise Bakery

## Watch
- Stripe fees for small businesses
- Google search changes for local businesses
- Squarespace and Wix pricing changes
"""


CONTRACTS = {
    "maria@sunrisebakery.example": """# Agreement: website refresh for Sunrise Bakery
Signed by Maria Lopez and Alex Rivera on September 12.

Price: $2,400, half up front, half on launch.

Included:
- Four pages: Home, Menu, About, Contact.
- Menu page with item names, descriptions and prices.
- Mobile-friendly layout.
- Two rounds of revisions on the design (layout, colours, sizes of existing elements).

Not included (quoted separately if wanted): online ordering, a blog, new photography, logo redesign.
""",
    "jordan@kimyoga.example": """# Agreement: Kim Yoga site
Signed by Jordan Kim and Alex Rivera on August 3.

Price: $1,800.

Included:
- Five pages including a class schedule and a contact form that emails Jordan.
- Fixing any bugs in the delivered pages for 60 days after launch.

Not included: online booking or payments, a members area.
""",
}


def money_book() -> dict:
    """Balance, invoices and bills. Priya pays about 12 days late, and at that pace the
    studio rent on the 1st doesn't clear: the cash guard should notice and say why."""
    return {
        "balance": 1240.0, "as_of": _d(0),
        "invoices": [
            {"number": "109", "client": "Priya Shah", "contact": "priya@shahdental.example", "amount": 600,
             "issued": _d(-84), "due": _d(-70), "paid_on": _d(-58)},
            {"number": "113", "client": "Priya Shah", "contact": "priya@shahdental.example", "amount": 700,
             "issued": _d(-53), "due": _d(-39), "paid_on": _d(-26)},
            {"number": "115", "client": "Jordan Kim", "contact": "jordan@kimyoga.example", "amount": 1800,
             "issued": _d(-60), "due": _d(-46), "paid_on": _d(-46)},
            {"number": "119", "client": "Noah Brooks", "contact": "noah@brookscoffee.example", "amount": 1600,
             "issued": _d(-15), "due": _d(-1), "paid_on": _d(-2)},
            {"number": "118", "client": "Priya Shah", "contact": "priya@shahdental.example", "amount": 850,
             "issued": _d(-16), "due": _d(-2), "paid_on": None},
            {"number": "121", "client": "Maria Lopez", "contact": "maria@sunrisebakery.example", "amount": 1200,
             "issued": _d(-4), "due": _d(17), "paid_on": None},
        ],
        "bills": [
            {"payee": "Hosting (HostingCo)", "amount": 36, "due": _d(2), "recurring": "monthly"},
            {"payee": "Business insurance", "amount": 420, "due": _d(6)},
            {"payee": "Studio rent", "amount": 900, "due": _d(8), "recurring": "monthly"},
            {"payee": "Design software", "amount": 54, "due": _d(12), "recurring": "monthly"},
        ],
    }


def _last_friday(weeks_back: int) -> date:
    d = date.today() - timedelta(weeks=weeks_back)
    return d - timedelta(days=(d.weekday() - 4) % 7)


def history() -> list[dict]:
    """Eight weeks of closed promises. The pattern in it is real enough to learn from:
    quotes for new leads, promised for Friday, keep landing on Monday or Tuesday."""
    rows, n = [], 0

    def closed(text, who, due, late, note, contact=""):
        nonlocal n
        n += 1
        done = due + timedelta(days=late)
        rows.append({"id": f"h{n:03d}", "text": text, "who": who, "due": due.isoformat(), "source": "",
                     "origin": "inbox", "contact": contact, "direction": "i_owe", "status": "done",
                     "created": f"{(due - timedelta(days=4)).isoformat()}T09:00:00+00:00",
                     "closed": f"{done.isoformat()}T16:30:00+00:00", "note": note, "history": []})

    leads = [("Send Hannah the quote for a clinic site", "Hannah Weiss", 8, 3),
             ("Send Omar rates and a timeline", "Omar Haddad", 7, 2),
             ("Send Lucia a quote for the shop redesign", "Lucia Ferri", 5, 0),
             ("Send Ben the estimate for a booking page", "Ben Carter", 4, 3),
             ("Send Aisha a quote for the gym site", "Aisha Bello", 2, 2),
             ("Send Tom rates for a 3-page site", "Tom Novak", 1, 4)]
    for text, who, wk, late in leads:
        contact = who.split(" ")[0].lower() + "@" + who.split(" ")[1].lower() + "studio.example"
        closed(text, who, _last_friday(wk), late, "Sent the quote" + (" late, apologised" if late else ""), contact)
    for wk in (8, 6, 4, 3, 1):
        closed(f"Fix a layout bug on the Kim Yoga site (week {wk})", "Jordan Kim",
               _last_friday(wk) - timedelta(days=2), 0, "Fixed and checked on mobile")
    for wk, text in ((7, "Send Maria the new menu photos"), (5, "Share the bakery logo files with Maria"),
                     (3, "Send Maria the holiday banner"), (2, "Update the bakery opening hours")):
        closed(text, "Maria Lopez", _last_friday(wk) - timedelta(days=1), 0, "Done the same day")
    closed("Launch the Brooks Coffee site", "Noah Brooks", date.today() - timedelta(days=1), 0,
           "Launched; DNS switched, forms tested", "noah@brookscoffee.example")
    closed("Reply to Sam about the Q2 receipts", "Sam Okafor", _last_friday(6) - timedelta(days=3), 1,
           "Replied a day late")
    return rows


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
    write_json("money.json", money_book())
    (d / "contracts").mkdir(exist_ok=True)
    for addr, text in CONTRACTS.items():
        (d / "contracts" / f"{addr}.md").write_text(text)
    y = (date.today() - timedelta(days=1)).isoformat()
    write_json("ledger.json", history() + [
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
