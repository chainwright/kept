"""Forty client messages a contractor really gets, on the live models, graded by code.

Kitchen jobs, other trades, other languages, off-topic chat, rudeness, haggling, an attempt to
override the rules, returning clients and a name that matches someone else's. For each one the
expected outcome is written down in eval/messages.json; code checks the reply against it.

    .venv/bin/python eval/run_messages.py [--only id1,id2]
"""
from __future__ import annotations

import argparse
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

CYR = re.compile(r"[а-яёіїєґ]", re.I)
UK = re.compile(r"[іїєґ]", re.I)
LANG = {"es": re.compile(r"\b(hola|gracias|cocina|puertas|precio|visita|saludos)\b", re.I),
        "fr": re.compile(r"\b(bonjour|merci|cuisine|crédence|prix|visite|cordialement)\b", re.I)}


def body_of(r) -> str:
    a = (r.get("reply") or {}).get("approval") or {}
    return (a.get("args") or {}).get("body", "")


def grade(case: dict, r: dict) -> dict:
    from kept.reply import _names_a_slot
    from kept.validators import dollar_amounts
    ex, b, p = case.get("expect", {}), body_of(r), r.get("plan") or {}
    c = {"answered": bool(b) or bool((r.get("growth") or {}).get("asks"))}
    if "off_topic" in ex:
        c["off_topic_as_expected"] = bool(p.get("off_topic")) == ex["off_topic"]
    if p.get("off_topic"):
        c["off_topic_has_no_prices_or_times"] = not dollar_amounts(b) and not _names_a_slot(b, p.get("slots") or [])
    for rx in ex.get("reply_any", []):
        c[f"says /{rx[:24]}/"] = bool(re.search(rx, b, re.I))
    for rx in ex.get("reply_none", []):
        c[f"never /{rx[:24]}/"] = not re.search(rx, b, re.I)
    for rx in ex.get("asks", []):
        c[f"asks /{rx[:20]}/"] = any(re.search(rx, a, re.I) for a in p.get("ask") or [])
    if ex.get("slots"):
        c["offers_a_visit_time"] = _names_a_slot(b, p.get("slots") or [])
    lang = ex.get("lang")
    if lang in ("ru", "uk"):
        c["answers_in_their_language"] = len(CYR.findall(b)) > len(re.findall(r"[a-z]", b, re.I)) and (lang == "ru" or bool(UK.search(b)))
    elif lang:
        c["answers_in_their_language"] = bool(LANG[lang].search(b))
    if "memory" in ex:
        c["remembers_them"] = bool(r.get("memory")) == ex["memory"]
    if "lookalike" in ex:
        c["flags_same_name"] = bool(r.get("lookalike")) == ex["lookalike"]
    c["signed_as_alex"] = (not b) or bool(re.search(r"\bAlex\b", b[-80:]))
    return c


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--only", default="")
    a = ap.parse_args()
    cases = json.loads((ROOT / "eval" / "messages.json").read_text())
    if a.only:
        cases = [c for c in cases if c["id"] in a.only.split(",")]
    E.fresh_modules(tempfile.mkdtemp(prefix="kept-messages-"))
    from kept import approvals, snapshot, store, tryit
    snapshot.restore()
    start = len(store.read_audit(100000))
    rows, t0 = [], time.time()
    for case in cases:
        t = time.time()
        try:
            r = tryit.handle(case.get("key", "new"), case["subject"], case["body"], case.get("name", ""), case.get("email", ""))
            c = grade(case, r)
            err = ""
        except Exception as e:
            r, c, err = {}, {"answered": False}, f"{type(e).__name__}: {e}"
        a_ = (r.get("reply") or {}).get("approval")
        if a_:   # Alex says Yes, as a judge would, so the next message from them is a follow-up
            approvals.decide(a_["id"], True)
        ok = all(c.values())
        rows.append({"id": case["id"], "group": case["group"], "ok": ok, "checks": c, "reply": body_of(r),
                     "plan": {k: (r.get("plan") or {}).get(k) for k in ("job", "off_topic", "ask")},
                     "held": r.get("held_back"), "error": err, "seconds": round(time.time() - t, 1)})
        print(f"{'PASS' if ok else 'FAIL'} {case['id']:<18} {sum(c.values())}/{len(c)} {round(time.time() - t, 1)}s "
              + ("" if ok else str([k for k, v in c.items() if not v])) + (f" {err}" if err else ""), flush=True)
    calls = [x for x in store.read_audit(100000)[start:] if x["kind"] == "llm"]
    usd = round(sum(x["usd"] for x in calls), 4)
    n_ok = sum(r["ok"] for r in rows)
    checks = sum(len(r["checks"]) for r in rows)
    checks_ok = sum(sum(r["checks"].values()) for r in rows)
    out = ROOT / "eval" / "results" / f"messages-{datetime.now():%Y%m%d-%H%M%S}.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps({"messages": len(rows), "messages_ok": n_ok, "checks": checks, "checks_ok": checks_ok,
                               "usd": usd, "seconds": round(time.time() - t0, 1), "rows": rows}, indent=1, ensure_ascii=False))
    print(f"\n{n_ok}/{len(rows)} messages fully right; {checks_ok}/{checks} checks; ${usd}; saved {out.relative_to(ROOT)}")


if __name__ == "__main__":
    main()
