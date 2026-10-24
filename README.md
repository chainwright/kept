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

1. **Reads the inbox** and sorts it (Nemotron Nano): leads, clients, bills, noise.
2. **Finds promises** in each thread (Nano) and adds them to the **commitment ledger**, but only
   if it can quote the exact words in the email that show the promise. If it can't point at
   the words, it isn't a promise.
3. **Drafts follow-ups** for anything overdue or due today (Nemotron Super), runs the draft
   through checks (no template holes, right name, sane length), and puts it in front of you
   with **Yes / No** buttons. Nothing is sent until you press Yes.
4. **Watches topics you care about** with Tavily web search. Super summarises, and a fact only
   reaches you if it quotes a page Kept actually fetched.
5. **Makes the one hard call** when the week has more promises than hours (Nemotron Ultra):
   which deadline should move, and a short honest note asking for the new date. That note also
   waits for your Yes.
6. **Writes the morning brief** (Super). Code checks it afterwards: a brief that forgets an
   overdue promise gets the promise put back at the top, marked "added by rule".

You can also **ask Kept about your own week** ("what did I promise Maria?"). It answers only
from its own records and shows the lines it relied on, with a Verified badge when every quote
checks out.

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
| sorting mail, extracting promises | **Nemotron 3 Nano** | cheap and fast; runs on every email |
| planning the day, drafting text, summarising news | **Nemotron 3 Super** | someone will read it, so quality matters |
| deciding which promise to break | **Nemotron 3 Ultra** | rare, and a wrong call costs trust or money |

Model IDs are discovered from `/v1/models` at start-up. A daily budget (default $1.00) stops
calls before they happen once it's reached.

_(Real numbers from our runs: cost per day, latency per tier, to be added.)_

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
with six emails. Tests: `.venv/bin/python -m pytest -q`.

## Limitations (honest list)

- It only knows what's in the inbox and its own files. Promises made on a phone call don't exist
  until you add them.
- The grounding check is lexical: a quote must match the source word for word. A model that
  paraphrases gets held back even when it's right. We chose false "no" over false "yes".
- One action type today (`send_email`). Calendar and invoices are next.
- Single user. No multi-tenant auth; run it for yourself.

## Privacy

Your data stays in files on your machine or server. The Token Factory project runs with
**zero data retention** switched on. Demo mode never sends mail.

## License

MIT
