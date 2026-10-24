"""Demo data: one week in the life of Alex, who remodels kitchens on their own.
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
        {"id": "demo:1", "from": "Maria Lopez <maria@lopezhome.example>", "date": _d(-3),
         "subject": "Re: kitchen remodel",
         "body": f"Hi Alex,\n\nThanks for coming by on Monday. You said you'd send the revised quote with the "
                 f"quartz countertop option by {_d(-1)}, so I can show it to my husband over the weekend.\n\n"
                 "Also, could the island have an outlet on the side? We'd like to plug in the mixer there.\n\nMaria"},
        {"id": "demo:2", "from": "Dev Patel <dev@patelfamily.example>", "date": _d(-1),
         "subject": "Kitchen in our old house",
         "body": "Hello, a neighbour gave me your name. We just bought a 1950s house and the kitchen needs "
                 f"a full redo: cabinets, counters, sink. Could you send me your rates and a rough timeline by {_d(2)}? "
                 "We'd like it done before my parents visit in the spring.\n\nThanks,\nDev"},
        {"id": "demo:3", "from": "Billing <billing@buildrent.example>", "date": _d(-2),
         "subject": "Invoice #4412 is due",
         "body": f"Your invoice #4412 for $36.00 (tile saw rental, one day) is due on {_d(2)}. "
                 "Please pay before the due date to keep your account in good standing."},
        {"id": "demo:4", "from": "Tile Trends <news@tiletrends.example>", "date": _d(-1),
         "subject": "10 backsplash ideas for this autumn",
         "body": "Our editors picked ten backsplash patterns your clients will love. Plus: a giveaway!"},
        {"id": "demo:5", "from": "Sam Okafor <sam@okaforcpa.example>", "date": _d(-1),
         "subject": "Q3 receipts",
         "body": f"Hi Alex, friendly reminder: please send me your Q3 receipts before {_d(1)} so I can "
                 "file on time. A zip or a shared folder is fine.\n\nSam"},
        {"id": "demo:7", "from": "Priya Shah <priya@shahdental.example>", "date": _d(-6),
         "subject": "Re: invoice #118",
         "body": f"Hi Alex, thanks for the reminder and sorry for the delay! Our office manager is back on "
                 f"Monday. We'll pay invoice #118 ($850) by {_d(-2)} at the latest.\n\nPriya"},
        {"id": "demo:8", "from": "Maria Lopez <maria@lopezhome.example>", "date": _d(0),
         "subject": "Two small things",
         "body": "Hi Alex! While you're here, could you also tile the backsplash behind the stove? And the new "
                 "pantry door doesn't close all the way, it bounces back open.\n\nThank you!! Maria"},
        {"id": "demo:9", "from": "Noah Brooks <noah@brookscoffee.example>", "date": _d(-1),
         "subject": "It looks amazing",
         "body": "Alex! We opened this morning with the new back counter and shelves, and three customers asked "
                 "who did it. The baristas say it's so much easier to work behind the bar now. You were great to "
                 "work with, thank you!\n\nNoah"},
        {"id": "demo:6", "from": "Jordan Kim <jordan@kimfamily.example>", "date": _d(0),
         "subject": "Walkthrough + dishwasher leak",
         "body": f"Hey Alex! Can we push our final walkthrough to {_d(2)}? Something came up on my side. "
                 "Also, last week you mentioned you'd fix the leak under the new sink this week. Is that still "
                 "the plan? It still drips into the cabinet when the dishwasher runs.\n\nJordan"},
    ]


NOTES = """# About the owner
Alex Rivera remodels kitchens in Portland, Oregon, working alone with a van, a workshop and a
trusted plumber and electrician to call. Clients are homeowners and small businesses that need a
kitchen, a staff kitchenette or a cafe counter.
Prefers short, friendly emails. Signs as "Alex". On job sites 8:00-16:00, answers email in the
evening, no site visits on Sundays.
- Business: a one-person kitchen remodeling business

## Rates
- Hourly rate: $85

## Services
- Full kitchen remodel (take everything out, new cabinets, countertop, backsplash): from $18,000, 3 to 5 weeks on site
- New cabinet fronts on the existing boxes: from $4,500, about a week
- New countertop: from $2,800
- New backsplash: from $1,200
- Cafe counters, shelving and staff kitchenettes: priced after a visit
- Small repairs (handles, hinges, latches, drawers, a door that won't close): $85 an hour, 2-hour minimum, plus hardware
- Hardware for repairs: standard parts, matched as closely as possible to the style in the client's photo
- Measuring visit: free, and needed before any price for fronts, countertops, backsplash or a full remodel
- Measuring visits: weekdays at 16:30 and 17:30, Saturdays at 10:00 and 11:30, never on Sundays

## Price guide (installed, for preliminary estimates)
- Cabinets, mid-range painted MDF: $1,100 per foot of wall with cabinets (base and wall units together)
- Cabinets, solid wood: $1,500 per foot of wall with cabinets
- Cabinet fronts, painted MDF: $250 each door or drawer front
- Cabinet fronts, solid wood: $380 each door or drawer front
- Countertop, laminate: $45 per square foot
- Countertop, quartz: $95 per square foot
- Backsplash, ceramic tile: $35 per square foot
- Backsplash, glass panel: $95 per square foot
- Taking out the old kitchen: $1,200
- Sink and faucet hookup: $600

## Ads
- Ad budget: up to $10 a day, at most 7 days, only when cash is short
- Ad places: Facebook and Instagram, people within 10 miles of Portland
- Ad audience: homeowners aged 30 to 65 interested in home improvement or kitchen remodeling

## Payment plans
- For jobs from $4,500: 30% up front, the rest in 12 equal monthly payments, written into the contract

## New clients
- Look for new clients: new cafe OR restaurant OR clinic OR shop opening {city} 2026
- What new clients need: a new kitchen, a cafe counter or a staff kitchenette

## Offers
- Max discount: 15%
- Minimum project price: $900
- One offer per client per 60 days

## Reviews and posts
- Review link: https://g.page/r/alex-rivera-remodeling/review
- Clients I may name in posts: Brooks Coffee

## Watch
- Lumber and cabinet prices in the Pacific Northwest
- Oregon contractor license and permit rules
- Home renovation demand in Portland
"""


CONTRACTS = {
    "maria@lopezhome.example": """# Agreement: kitchen remodel for Maria Lopez
Signed by Maria Lopez and Alex Rivera on September 12.

Price: $19,400, a third up front, a third at cabinet install, a third on completion.

Included:
- Remove the old cabinets and countertops.
- Install 14 new cabinets and a kitchen island.
- Laminate countertops (quartz quoted separately on request).
- Reconnect the sink, faucet and dishwasher.
- Adjusting cabinet doors and drawers so they close properly, for 30 days after install.

Not included (quoted separately if wanted): backsplash tile, electrical work or new outlets,
appliances, flooring, painting.
""",
    "jordan@kimfamily.example": """# Agreement: new cabinet fronts and countertops for Jordan Kim
Signed by Jordan Kim and Alex Rivera on August 3.

Price: $11,800.

Included:
- New fronts on all cabinets, a quartz countertop, a new undermount sink and faucet.
- Fixing leaks or defects in the delivered work for 60 days after completion.

Not included: new appliances, moving plumbing, flooring, painting outside the kitchen.
""",
}


def money_book() -> dict:
    """Balance, invoices and bills. Priya pays about 12 days late, and at that pace the
    workshop rent on the 1st doesn't clear: the cash guard should notice and say why."""
    return {
        "balance": 1240.0, "as_of": _d(0),
        "invoices": [
            # Lucia hired Alex after that quote (a staff kitchenette for her shop), paid early and hasn't
            # ordered since: the one client a well-timed offer suits (a boutique, ahead of the holidays)
            {"number": "104", "client": "Lucia Ferri", "contact": "lucia@ferriboutique.example", "amount": 1400,
             "issued": _d(-130), "due": _d(-116), "paid_on": _d(-118)},
            # Ben took the cabinet estimate, then only had the drawers and two hinges fixed: a past
            # client worth a friendly check-in a month or so later
            {"number": "107", "client": "Ben Carter", "contact": "ben@carterhome.example", "amount": 255,
             "issued": _d(-45), "due": _d(-31), "paid_on": _d(-40)},
            {"number": "109", "client": "Priya Shah", "contact": "priya@shahdental.example", "amount": 600,
             "issued": _d(-84), "due": _d(-70), "paid_on": _d(-58)},
            {"number": "113", "client": "Priya Shah", "contact": "priya@shahdental.example", "amount": 700,
             "issued": _d(-53), "due": _d(-39), "paid_on": _d(-26)},
            {"number": "115", "client": "Jordan Kim", "contact": "jordan@kimfamily.example", "amount": 3800,
             "issued": _d(-60), "due": _d(-46), "paid_on": _d(-46)},
            {"number": "119", "client": "Noah Brooks", "contact": "noah@brookscoffee.example", "amount": 1600,
             "issued": _d(-15), "due": _d(-1), "paid_on": _d(-2)},
            {"number": "118", "client": "Priya Shah", "contact": "priya@shahdental.example", "amount": 850,
             "issued": _d(-16), "due": _d(-2), "paid_on": None},
            {"number": "121", "client": "Maria Lopez", "contact": "maria@lopezhome.example", "amount": 6467,
             "issued": _d(-4), "due": _d(17), "paid_on": None},
        ],
        "bills": [
            {"payee": "Tile saw rental (BuildRent)", "amount": 36, "due": _d(2)},
            {"payee": "Van insurance", "amount": 420, "due": _d(6)},
            {"payee": "Workshop rent", "amount": 900, "due": _d(8), "recurring": "monthly"},
            {"payee": "Estimating software", "amount": 54, "due": _d(12), "recurring": "monthly"},
        ],
    }


def _last_friday(weeks_back: int) -> date:
    d = date.today() - timedelta(weeks=weeks_back)
    return d - timedelta(days=(d.weekday() - 4) % 7)


def history() -> list[dict]:
    """Eight weeks of closed promises. The pattern in it is real enough to learn from:
    quotes and estimates for new leads, promised for Friday, keep landing on Monday or Tuesday."""
    rows, n = [], 0

    def closed(text, who, due, late, note, contact=""):
        nonlocal n
        n += 1
        done = due + timedelta(days=late)
        rows.append({"id": f"h{n:03d}", "text": text, "who": who, "due": due.isoformat(), "source": "",
                     "origin": "inbox", "contact": contact, "direction": "i_owe", "status": "done",
                     "created": f"{(due - timedelta(days=4)).isoformat()}T09:00:00+00:00",
                     "closed": f"{done.isoformat()}T16:30:00+00:00", "note": note, "history": []})

    leads = [("Send Hannah the estimate for a kitchen remodel", "Hannah Weiss", 8, 3),
             ("Send Omar rates and a timeline for his kitchen", "Omar Haddad", 7, 2),
             ("Send Lucia a quote for the staff kitchenette", "Lucia Ferri", 5, 0),
             ("Send Ben the estimate for new kitchen cabinets", "Ben Carter", 4, 3),
             ("Send Aisha a quote for the gym's staff kitchen", "Aisha Bello", 2, 2),
             ("Send Tom rates for a countertop swap", "Tom Novak", 1, 4)]
    for text, who, wk, late in leads:
        contact = {"Lucia Ferri": "lucia@ferriboutique.example"}.get(
            who, who.split(" ")[0].lower() + "@" + who.split(" ")[1].lower() + "home.example")
        closed(text, who, _last_friday(wk), late, "Sent the quote" + (" late, apologised" if late else ""), contact)
    for wk, text in ((8, "Send Jordan the cabinet front samples"), (6, "Confirm the countertop template with Jordan"),
                     (4, "Install Jordan's new cabinet fronts"), (3, "Install Jordan's countertop and sink"),
                     (1, "Fix the loose drawer pull for Jordan")):
        closed(text, "Jordan Kim", _last_friday(wk) - timedelta(days=2), 0, "Done and checked")
    for wk, text in ((7, "Send Maria the cabinet colour samples"), (5, "Confirm the cabinet delivery date with Maria"),
                     (3, "Send Maria photos of the island layout"), (2, "Order Maria's sink and faucet")):
        closed(text, "Maria Lopez", _last_friday(wk) - timedelta(days=1), 0, "Done the same day")
    closed("Fix Ben's drawer slides and two cabinet hinges", "Ben Carter", date.today() - timedelta(days=42), 0,
           "Fixed in one visit, 3 hours; hardware matched to his brushed-nickel handles", "ben@carterhome.example")
    closed("Finish the Brooks Coffee back counter", "Noah Brooks", date.today() - timedelta(days=1), 0,
           "Counter and shelves in, sealed, cleaned up", "noah@brookscoffee.example")
    closed("Reply to Sam about the Q2 receipts", "Sam Okafor", _last_friday(6) - timedelta(days=3), 1,
           "Replied a day late")
    return rows


def calendar_book() -> dict:
    """Alex's next two weeks: days on Maria's job, one visit already booked."""
    ev = []
    for i in range(1, 15):
        d = date.today() + timedelta(days=i)
        if d.weekday() < 5 and i <= 9:
            ev.append({"id": f"site{i:02d}", "date": d.isoformat(), "kind": "site", "who": "Maria Lopez",
                       "what": "On site: Lopez kitchen (cabinets and island)"})
    first_weekday = next(date.today() + timedelta(days=i) for i in range(1, 8) if (date.today() + timedelta(days=i)).weekday() < 5)
    ev.append({"id": "visit01", "date": first_weekday.isoformat(), "time": "16:30", "kind": "visit", "who": "Hannah Weiss",
               "contact": "hannah@weisshome.example", "what": "Measure for new countertop"})
    return {"events": ev, "offered": {}}


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
    write_json("calendar.json", calendar_book())
    from .config import ROOT
    from .media import copy_demo
    copy_demo("Noah Brooks", ROOT / "demo_media" / "brooks-before.jpg", ROOT / "demo_media" / "brooks-after.jpg")
    (d / "contracts").mkdir(exist_ok=True)
    for addr, text in CONTRACTS.items():
        (d / "contracts" / f"{addr}.md").write_text(text)
    y = (date.today() - timedelta(days=1)).isoformat()
    write_json("ledger.json", history() + [
        {"id": "a1c0de01", "text": "Send Jordan the care guide for the quartz countertop", "who": "Jordan Kim", "due": y,
         "source": "", "origin": "owner", "status": "done", "created": f"{_d(-4)}T16:00:00+00:00",
         "closed": f"{y}T17:40:00+00:00", "note": "Emailed the care guide and cleaning tips; Jordan replied thanks",
         "history": []},
        {"id": "a1c0de02", "text": "Book the countertop template visit for Maria", "who": "Maria Lopez", "due": _d(3),
         "source": "", "origin": "owner", "status": "open", "created": f"{_d(-5)}T10:00:00+00:00",
         "history": []},
    ])
    (d / "journal" / f"{y}.md").write_text(
        f"# {y}\n\n- 07:30 Morning brief: two promises due, one overdue\n"
        "- 17:40 Closed a1c0de01 as done: Emailed the care guide and cleaning tips; Jordan replied thanks\n")


if __name__ == "__main__":
    seed(force=True)
    print("demo data written to", data_dir())
