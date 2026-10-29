"""Grade "Write to Alex" on the live models: six client emails, checked by code.

Each run starts from the recorded morning, plays the same conversations a judge would, and checks
the outcome with plain rules (the job, the price, the times, the booking, the reply). Nothing here
asks a model whether it did well.

    .venv/bin/python eval/run_clients.py --runs 3
"""
from __future__ import annotations

import argparse
import base64
import json
import re
import sys
import tempfile
import time
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(Path(__file__).resolve().parent))
import run_eval as E  # noqa: E402


def img(name: str) -> str:
    return "data:image/jpeg;base64," + base64.b64encode((ROOT / "demo_media" / name).read_bytes()).decode()


def body_of(r) -> str:
    a = (r.get("reply") or {}).get("approval") or {}
    return (a.get("args") or {}).get("body", "")


def run_once() -> dict:
    E.fresh_modules(tempfile.mkdtemp(prefix="kept-clients-"))
    from kept import approvals, ledger, schedule, snapshot, tryit
    from kept import democlock
    democlock.install()  # the same frozen calendar the live demo runs on
    snapshot.restore()
    from kept import store
    audit_start = len(store.read_audit(100000))  # the recorded morning's own calls aren't this run's cost
    c, t0, log = {}, time.time(), {}
    jo = dict(name="Jo Rivera", email="jo@riverahome.example")

    r = tryit.handle("new", "Our old kitchen", "Hi Alex, we just bought a house and the kitchen is from the 90s "
                     "(photo attached). We'd love it to look modern. What would you suggest, and roughly what would "
                     "it cost?\n\nThanks, Jo", image=img("old-kitchen.jpg"), **jo)
    p, b = r.get("plan") or {}, body_of(r)
    est = p.get("estimate") or {}
    c["photo_read"] = bool((r.get("photo") or {}).get("seen"))
    c["kitchen_job"] = p.get("job") in ("full_kitchen", "fronts")
    c["estimate_from_guide"] = bool(est) and est["low"] <= est["mid"] <= est["high"]
    log["jo_first"] = {"plan": p, "photo": (r.get("photo") or {}).get("seen"), "reply": b}
    c["three_visit_times"] = len(p.get("slots") or []) == 3
    from kept.reply import _names_a_slot
    from kept.validators import dollar_amounts
    c["reply_has_a_time_and_price"] = bool(b) and _names_a_slot(b, p.get("slots") or []) \
        and bool(dollar_amounts(b) & {est.get("low"), est.get("mid"), est.get("high"), p.get("from_price")})
    if (r.get("reply") or {}).get("approval"):
        approvals.decide(r["reply"]["approval"]["id"], True)

    r = tryit.handle("new", "Re: Our old kitchen", "Hmm, that's a lot more than we expected. We just bought the "
                     "house and can't pay that much at once.", **jo)
    pp = (r.get("plan") or {}).get("payment_plan")
    b = body_of(r)
    log["objection"] = {"plan": r.get("plan"), "reply": b, "held": r.get("held_back")}
    c["payment_plan_offered"] = bool(pp) and bool(b) and (f"${pp['monthly']:,}" in b or f"${pp['monthly']}" in b)
    if (r.get("reply") or {}).get("approval"):
        approvals.decide(r["reply"]["approval"]["id"], True)

    offered = schedule.load().get("offered", {}).get("jo@riverahome.example") or []
    if offered:
        lab = offered[0]["label"]
        r = tryit.handle("new", "Re: visit", f"OK. {lab.split(',')[0]} at {lab.split(' at ')[1]} works.", **jo)
        c["visit_booked"] = any(e.get("who") == "Jo Rivera" and e["date"] == offered[0]["date"] for e in schedule.upcoming())
        c["booking_confirmed_in_reply"] = lab.split(",")[0] in body_of(r)
    else:
        c["visit_booked"] = c["booking_confirmed_in_reply"] = False

    r = tryit.handle("new", "Cabinet door under the sink", "Hello, the cabinet door under our sink came off its hinge "
                     "and the drawer below is loose. Could you fix it? We're in Sellwood. Photo attached.\n\nSam",
                     name="Sam Lee", email="sam.lee@example.com", image=img("cabinet-repair.jpg"))
    p, b = r.get("plan") or {}, body_of(r)
    c["repair_priced_now"] = p.get("job") == "small_repair" and p.get("price", 0) >= 170 and f"${p.get('price')}" in b

    r = tryit.handle("maria", "Two more things", "Hi Alex! While you're here, could you also tile the backsplash "
                     "behind the stove? And the new pantry door doesn't close all the way.\n\nMaria")
    reqs = {E.norm(x["request"]): x["verdict"] for x in (r.get("scope") or {}).get("requests", [])}
    c["backsplash_not_free"] = any("backsplash" in k and v in ("out_of_scope", "unclear") for k, v in reqs.items())
    c["pantry_door_not_sold"] = not any("pantry" in k and v == "out_of_scope" for k, v in reqs.items())
    b = body_of(r)
    c["maria_got_a_reply"] = bool(b)
    # covered work is free, and extra work is offered, not announced
    c["maria_asked_not_told"] = bool(b) and bool(re.search(r"\?|let me know|would you like|shall i", b, re.I)) \
        and not re.search(r"pantry[^.]*\$\d", b, re.I)
    log["maria"] = {"reply": b, "scope": r.get("scope"), "plan": r.get("plan")}

    r = tryit.handle("priya", "Re: invoice #118", "Hi Alex, so sorry again. Our office manager is back, we will pay "
                     "invoice #118 next Wednesday.\n\nPriya")
    rows = [x for x in ledger.items("open") if "118" in x["text"] and x.get("direction") == "owed_to_me"]
    c["priya_one_row_with_new_date"] = len(rows) == 1 and any("promised again" in h.get("event", "") for h in rows[0].get("history", []))

    calls = [a for a in store.read_audit(100000)[audit_start:] if a["kind"] == "llm"]
    usd = sum(a["usd"] for a in calls)
    c["nothing_sent_without_yes"] = all(a["status"] in ("pending", "done", "replaced", "rejected") for a in approvals.recent(1000))
    return {"checks": c, "usd": round(usd, 4), "seconds": round(time.time() - t0, 1),
            "log": log}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--runs", type=int, default=3)
    a = ap.parse_args()
    results = []
    for n in range(a.runs):
        try:
            g = run_once()
        except Exception as e:
            g = {"crash": f"{type(e).__name__}: {e}"}
        g["run"] = n + 1
        results.append(g)
        ok = sum(g.get("checks", {}).values())
        print(f"run {n + 1}: {ok}/{len(g.get('checks', {}))}, ${g.get('usd')}, {g.get('seconds')}s "
              + (g.get("crash", "") or ""), flush=True)
    names = sorted({k for r in results for k in r.get("checks", {})})
    summary = {k: f"{sum(1 for r in results if r.get('checks', {}).get(k))}/{len(results)}" for k in names}
    out = ROOT / "eval" / "results" / f"clients-{datetime.now():%Y%m%d-%H%M}.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps({"summary": summary, "runs": results}, indent=1, ensure_ascii=False))
    print("\nPASS RATES")
    for k in names:
        print(f"  {summary[k]:>6}  {k}")
    print(f"total ${sum(r.get('usd', 0) for r in results):.3f}; saved {out.relative_to(ROOT)}")


if __name__ == "__main__":
    main()
