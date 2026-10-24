# Kept

**An always-on operator for one-person businesses. It remembers every promise you make,
checks its own work, and does nothing that reaches another person until you say Yes.**

Built for the Nebius × NVIDIA Global AI Hackathon, Personal AI track.
Runs on **Nebius Token Factory** with **NVIDIA Nemotron 3** (Nano, Super and Ultra).

---

## Why this exists

If you work alone, your business runs on promises. "I'll send the quote by Thursday." "Let me
check and get back to you." Each one is small. Together they decide whether clients trust you.
They also live in five places at once: the inbox, a notes app, a sticky note, your head.

We run a small agency where agents have been doing this kind of daily work for months. Two
lessons from that shaped Kept:

1. **An assistant that sometimes invents things is worse than none.** You stop trusting it, and
   then you check everything twice.
2. **An assistant that acts behind your back gets switched off.** You only hand over the keys
   when you know nothing leaves without your say-so.

So Kept is built around restraint: it proposes, code verifies, and when a check fails it holds
back and tells you why.

## What it does every morning

Kept reads the inbox and runs nine skills. Each one ends in a proposal waiting for your Yes, a
line in the morning brief, or an entry under **Held back** saying what it refused to do and why.

**Your word**
1. **Promise ledger, both ways**: what you owe and what you're owed, each with the exact words
   from the email (Nemotron Super extracts, code checks the quote).
2. **Calibration** from your closed promises, and **Before you send**: paste a reply, Kept finds
   the promise (Nano), works out the date in code and suggests the day you'll actually hit.
3. **Rules it learns** (Ultra proposes a pattern; code recounts every match; needs 4+ matches and
   60% late; you approve; it's appended to the skill file).

**Your time**
4. **Scope guard**: Ultra reads the signed agreement twice (two temperatures); disagreement means
   "unclear". Extra work is priced by code from your hourly rate.
5. **Overload call**: when promises exceed hours, Ultra picks the one deadline that can move and
   drafts an honest note. Hard deadlines are never moved.

**Your money**
6. **Cash guard**: 30-day forecast using each client's usual payment delay; reminder ladder
   (friendly, firm, final) checked for the right invoice number and amount.
7. **Rescue plan**: when the forecast goes below zero, what closes the gap fastest from your own
   pipeline, plus new local prospects found with Tavily (the page must name the business).
8. **Well-timed offers**: a calendar computed by code, your own limits from `notes.md` (max
   discount, minimum price, one offer per 60 days); nobody who owes you or whom you owe work.
9. **Growth without spam**: a review ask when a client is delighted (never while a project is
   unpaid or your last delivery was late), and a before/after post using only sourced numbers.

Plus **topic watch** (Tavily, grounded quotes only) and **Ask Kept** about your own week.

## Propose, verify, or abstain

| Model output | Checked by code | If the check fails |
|---|---|---|
| Promise found in an email | the quoted words must appear in that email; due date must parse and be plausible | not added; reason shown under **Held back** |
| Follow-up draft | JSON shape; no `[Name]`-style holes; mentions the person; length limit | no approval request; reason shown |
| News fact | must quote a page returned by the search, word for word | dropped; counted as "couldn't verify" |
| Morning brief | every reference must exist; every overdue promise must be mentioned | bad references removed; missing promises added by rule |
| "Move this deadline" decision | must pick one of this week's promises; new date sane; real email address | no request; reason shown |
| Answer about your week | every quote must appear in the cited ledger row or journal | shown as **Not verified** |

None of these checks ask a model whether it did well. They are plain code (`kept/validators.py`),
and the tests in `tests/` show each one catching a bad output.

## The approval gate is code, not a prompt

`kept/approvals.py` keeps a registry of actions. Anything that leaves the machine (today:
`send_email`) is registered as needing approval, and the only way to run it is `execute()`,
which refuses anything that isn't approved. The model can propose whatever it likes; it has no
path to run it. Decisions come from the web dashboard or, optionally, from Yes / No buttons in
your own Telegram bot.

In demo mode, approved mail is written to `data/outbox/` instead of being sent, so anyone can
press Yes safely.

## How Kept uses Nebius Token Factory and Nemotron

Every call goes to Token Factory's OpenAI-compatible endpoint
(`https://api.tokenfactory.nebius.com/v1/`). The router (`kept/llm.py`) picks the model by the
kind of work, and every call is logged with its tier, reason, tokens, latency and cost:

| Work | Tier | Why |
|---|---|---|
| sorting mail, spotting promises in a draft | **Nemotron 3 Nano** (reasoning off) | cheap and fast; runs on every email |
| extracting promises, planning the day, drafting, summarising news | **Nemotron 3 Super** | someone will read it, so quality matters |
| scope, overload, learned rules, rescue ranking, offers | **Nemotron 3 Ultra** | rare, and a wrong call costs trust or money |

Model IDs are discovered from `/v1/models` at start-up. A daily budget (default $1.00) stops
calls before they happen once it's reached.

A full demo morning is about 40-43 calls (14 Nano, 19-21 Super, 7-8 Ultra) and costs $0.05-0.07,
measured by `eval/run_eval.py` on the live models.

## Memory you can read

Everything Kept knows is in plain files under `data/`:

- `ledger.json`: every promise, open or closed, with who it's owed to and how it ended
- `journal/YYYY-MM-DD.md`: what Kept did and decided each day
- `notes.md`: facts about you and your business, plus the topics to watch
- `audit.jsonl`: every model call and every action

Closing a promise needs a resolution (`done`, `dropped`, `handed_off`) and a note. "Forgot" is
not a state.

## Skills you can edit

`skills/*.md` are short rule sheets (how to sort mail, how to write a follow-up, what counts as
a promise, how the brief is laid out). They are added to the prompts that use them. Change the
markdown, and Kept's behaviour changes with it, without touching code.

## Run it

```bash
cp .env.example .env          # add NEBIUS_API_KEY (and TAVILY_API_KEY for news)
python -m venv .venv && .venv/bin/pip install -r requirements.txt
.venv/bin/uvicorn kept.web:app --port 8000
# open http://localhost:8000 and press "Run morning loop"
```

Demo mode (`KEPT_DEMO=1`, the default) loads a made-up week for Alex, a freelance web designer,
with nine emails, two signed agreements, a money book and eight weeks of history.
Tests: `.venv/bin/python -m pytest -q`. Live evaluation (costs model credits):
`.venv/bin/python eval/run_eval.py --runs 5` grades each full day with 24 checks written in code.

## What live testing taught us

Our first runs on the real models went badly, and we kept the evidence because it shaped the design:

- **Every email got held back.** Nemotron Nano spent its whole token budget reasoning and returned an
  empty answer. Kept didn't guess; it logged "model reply unusable" for each one. Fix: Nano runs with
  reasoning switched off, Super and Ultra get extra room to think.
- **A promise was "owed to" the owner.** The model filled in the owner's name as the person waiting,
  so the follow-up started "Hi Alex" (that's the sender) and promised a date that had already passed.
  Fix: who the promise is owed to and their address now come from the email header, by code; a new
  check holds back drafts that greet the sender or mention a past date.
- **Ultra emailed an address it made up.** Fix: Ultra picks *which* promise to move; the address
  always comes from the original email.
- **Ultra told an accountant a delay "has no impact on your filing".** It only saw a one-line title.
  Fix: Ultra now reads each person's own words, and is told never to move someone's hard deadline.
  Its next decision moved the only promise without one, and its reasoning is saved next to it.
- **Two contradicting emails waited for approval** ("it's coming today" and "can we move it to
  Monday?"). Fix: a promise that already has a message waiting is off-limits to other jobs.

Each of these has a regression test in `tests/`.

## Limitations (honest list)

- It only knows what's in the inbox and its own files. Promises made on a phone call don't exist
  until you add them.
- The grounding check is lexical: a quote must match the source word for word. A model that
  paraphrases gets held back even when it's right. We chose false "no" over false "yes".
- One outgoing action today (`send_email`; posts go to an outbox). Calendar and invoices are next.
- Single user. No multi-tenant auth; run it for yourself.

## Privacy

Your data stays in files on your machine or server. The Token Factory project runs with
**zero data retention** switched on. Demo mode never sends mail.

## License

MIT
