"""Run the whole Kept day N times on live Nemotron and grade every run with code.

Each run starts from a fresh copy of the demo week, runs the morning loop, and then
checks the result against what a careful human would expect from that week. Nothing
here asks a model whether it did well.

    .venv/bin/python eval/run_eval.py --runs 8 [--skip-web]
Writes eval/results/<timestamp>.json and prints a pass-rate table.
"""
from __future__ import annotations

import argparse
import importlib
import json
import os
import re
import shutil
import sys
import tempfile
import time
from datetime import date, datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))


def fresh_modules(data_dir: str):
    os.environ["KEPT_DATA_DIR"] = data_dir
    for name in list(sys.modules):
        if name == "kept" or name.startswith("kept."):
            del sys.modules[name]
    import kept.agent  # noqa: F401  (re-import with the new data dir)
    return importlib.import_module("kept")


def norm(s: str) -> str:
    return re.sub(r"\s+", " ", (s or "").lower())


def has(rows, who_word, *words, direction=None):
    for r in rows:
        t = norm(r["text"] + " " + r.get("who", ""))
        if who_word.lower() in t and all(w in t for w in words):
            if direction is None or (r.get("direction") or "i_owe") == direction:
                return True
    return False


def grade(k) -> dict:
    from kept import approvals, ledger, money, store
    from kept.validators import honest_email
    open_rows = ledger.items("open")
    pend = approvals.pending()
    decided = [a for a in approvals.recent(200) if a["status"] != "pending"]
    inbox = {m["id"]: m for m in json.loads((store.data_dir() / "inbox.json").read_text())}
    known_addrs = {re.search(r"<([^>]+)>", m["from"]).group(1).lower() for m in inbox.values() if "<" in m["from"]}
    known_addrs |= {i["contact"].lower() for i in money.load()["invoices"]}
    known_addrs |= {r.get("contact", "").lower() for r in ledger.items() if r.get("contact")}
    emails = [a for a in pend if a["kind"] == "send_email"]
    c = {}

    # --- the ledger: promises found, in the right direction
    c["finds_maria_quote"] = has(open_rows, "maria", "quote", direction="i_owe")
    c["finds_dev_rates"] = has(open_rows, "dev", "rate", direction="i_owe")
    c["finds_sam_receipts"] = has(open_rows, "sam", "receipt", direction="i_owe")
    c["finds_jordan_leak_fix"] = has(open_rows, "jordan", "leak", direction="i_owe") or has(open_rows, "jordan", "sink", direction="i_owe")
    c["priya_owes_not_me"] = not has(open_rows, "priya", "118", direction="i_owe")
    c["backsplash_not_a_promise"] = not any("backsplash" in norm(r["text"]) and (r.get("direction") or "i_owe") == "i_owe"
                                             for r in open_rows)
    c["no_one_word_promises"] = all(len(r["text"].split()) >= 3 for r in open_rows)

    # --- the gate and the emails waiting for Yes
    c["nothing_sent_without_yes"] = not decided and not list((store.data_dir() / "outbox").glob("*.json"))
    c["recipients_are_real"] = all(a["args"]["to"].lower() in known_addrs for a in emails)
    c["one_email_per_person"] = len({a["args"]["to"].lower() for a in emails}) == len(emails)
    # a reminder may name the invoice's own (past) due date, exactly as money.chase allows
    due_by_no = {str(i["number"]): date.fromisoformat(i["due"][:10]) for i in money.load()["invoices"]}
    dishonest = []
    for a in emails:
        first = a["args"]["to"].split("@")[0].split(".")[0]
        body = a["args"]["body"]
        greet = re.match(r"\s*(hi|hello|hey|dear)\s+([A-Za-z]+)", body, re.I)
        allowed = {date.fromisoformat(x) for x in re.findall(r"20\d\d-\d\d-\d\d", a.get("why", ""))}
        if a["args"].get("invoice"):
            allowed.add(due_by_no.get(str(a["args"]["invoice"]).lstrip("#")))
        v = honest_email(body, recipient_first=greet.group(2) if greet else first, owner_first="Alex",
                         allowed_dates=allowed)
        if greet and greet.group(2).lower() == "alex":
            v.add("greets the owner")
        if not v:
            dishonest.append({"summary": a["summary"], "problems": v.problems, "body": body})
    c["emails_pass_honesty_checks"] = not dishonest

    # --- money
    f = money.forecast(30)
    c["cash_gap_found"] = bool(f["short"]) and abs(f["short"]["gap"] - 116) < 1
    rescue = store.read_json("rescue.json", {}) or {}
    # the gap is closed by money that's already real: Priya's overdue invoice, or extra work already priced
    c["rescue_closes_gap_with_real_money"] = str(rescue.get("closes_gap_at") or "").startswith(("invoice:118", "offer:"))
    reminders = [a for a in emails if a["args"].get("invoice")]
    c["priya_reminder_has_amount"] = all("$850" in a["args"]["body"] and "118" in a["args"]["body"] for a in reminders)

    # --- scope
    scope = store.read_json("scope.json", [])
    verdicts = {norm(r["request"]): r["verdict"] for s in scope for r in s["requests"]}
    c["backsplash_judged_out_or_unclear"] = any("backsplash" in k and v in ("out_of_scope", "unclear") for k, v in verdicts.items())
    c["pantry_door_not_sold"] = not any("pantry" in k and v == "out_of_scope" for k, v in verdicts.items())
    offers_for_scope = [a for a in emails if "extra work" in a["summary"]]
    c["scope_prices_computed"] = all(
        all(int(p) in {int(r.get("price") or 0) for s in scope for r in s["requests"]} | {sum(int(r.get("price") or 0) for r in s["requests"]) for s in scope}
            for p in re.findall(r"\$(\d+)", a["args"]["body"].replace(",", "")))
        for a in offers_for_scope)

    # --- restraint
    plan = store.read_json("offers_plan.json", {}) or {}
    skipped = {s["client"]: s["why_not"] for s in plan.get("skipped", [])}
    c["no_offer_to_priya"] = "Priya Shah" in skipped
    c["no_offer_while_owing_work"] = all(not (a["args"].get("offer_client") in ("Jordan Kim", "Maria Lopez")) for a in emails)
    c["offers_only_to_lucia"] = all(a["args"].get("offer_client") in (None, "Lucia Ferri") for a in emails)
    c["checkin_only_to_ben"] = any("Check in with Ben Carter" in a["summary"] for a in pend) and \
        not any(a["summary"].startswith("Check in with") and "Ben Carter" not in a["summary"]
                and "old quote" not in a["summary"] for a in pend)
    growth = store.read_json("growth_last.json", {}) or {}
    c["noah_review_or_waiting"] = bool(growth.get("asks")) or any(w["client"] == "Noah Brooks" for w in growth.get("waiting", []))
    c["no_review_ask_maria"] = not any("review" in a["summary"].lower() and "maria" in a["summary"].lower() for a in pend)

    # --- brief
    brief = store.read_json("brief.json", {}) or {}
    lines = norm(" ".join(l.get("text", "") for l in brief.get("lines", [])))
    c["brief_mentions_overdue"] = "maria" in lines or "quote" in lines
    c["brief_plan_grounded"] = all(isinstance(p, dict) and p.get("ref") for p in brief.get("plan", []))

    calls = [a for a in store.read_audit(5000) if a["kind"] == "llm"]
    usd = sum(a["usd"] for a in calls)
    c["new_lead_answered"] = any(a["args"].get("to") == "dev@patelfamily.example" for a in emails)
    # people Alex already deals with get a real answer, never the "I specialize in kitchens" line for strangers
    c["known_people_answered_on_topic"] = not any(
        a["args"].get("to", "").lower() in known_addrs and re.search(r"I speciali[sz]e in|easiest way to start", a["args"].get("body", ""))
        for a in emails)
    from kept.validators import iso_dates, wrong_weekdays
    c["dates_written_right"] = not any(iso_dates(a["args"].get("body", "")) or wrong_weekdays(a["args"].get("body", ""), date.today())
                                       for a in emails)
    c["cost_under_15_cents"] = usd < 0.15
    held = store.read_json("abstained.json", [])
    return {"checks": c, "usd": round(usd, 4), "calls": len(calls), "dishonest": dishonest,
            "brief_lines": [l.get("text", "") for l in brief.get("lines", [])],
            "tiers": {t: sum(1 for a in calls if a["tier"] == t) for t in ("nano", "super", "ultra")},
            "held_back": [{"job": h["job"], "subject": h["subject"][:60], "problems": h["problems"]} for h in held],
            "pending": [a["summary"] for a in pend], "open": [r["text"] for r in open_rows]}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--runs", type=int, default=5)
    ap.add_argument("--skip-web", action="store_true", help="skip Tavily-based jobs to save credits")
    a = ap.parse_args()
    out_dir = ROOT / "eval" / "results"
    out_dir.mkdir(parents=True, exist_ok=True)
    results = []
    for n in range(a.runs):
        d = tempfile.mkdtemp(prefix=f"kept-eval-{n}-")
        try:
            fresh_modules(d)
            from kept.seed import seed
            from kept import agent
            seed(force=True)
            if a.skip_web:
                import kept.agent as ag
                import kept.rescue as rs
                ag.watch_topics = lambda *x, **y: {"skipped": True}
                rs.find_prospects = lambda *x, **y: []
            t0 = time.time()
            out = agent.run_day()
            g = grade(None)
            errors = {k: v for k, v in out.items() if isinstance(v, str)}
            g["checks"]["no_job_failed"] = not errors  # a crashed job must fail the run, not hide in a log
            g.update({"run": n + 1, "seconds": round(time.time() - t0, 1), "job_errors": errors})
        except Exception as e:
            g = {"run": n + 1, "crash": f"{type(e).__name__}: {e}"}
        results.append(g)
        ok = sum(g.get("checks", {}).values()) if "checks" in g else 0
        print(f"run {n + 1}: {ok}/{len(g.get('checks', {}))} checks, ${g.get('usd')}, {g.get('seconds')}s "
              + (f"CRASH {g['crash']}" if "crash" in g else ""), flush=True)
        shutil.rmtree(d, ignore_errors=True)
    names = sorted({k for r in results for k in r.get("checks", {})})
    summary = {k: f"{sum(1 for r in results if r.get('checks', {}).get(k))}/{len(results)}" for k in names}
    stamp = datetime.now().strftime("%Y%m%d-%H%M")
    (out_dir / f"{stamp}.json").write_text(json.dumps({"summary": summary, "runs": results}, indent=1, ensure_ascii=False))
    print("\nPASS RATES")
    for k in names:
        print(f"  {summary[k]:>6}  {k}")
    print(f"\ntotal ${sum(r.get('usd', 0) for r in results):.3f}; saved eval/results/{stamp}.json")


if __name__ == "__main__":
    main()
