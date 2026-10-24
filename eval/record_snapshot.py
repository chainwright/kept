"""Record the demo's starting state from one real morning on Nemotron.

Runs the full day plus the weekly rule-learning job on a fresh demo week, grades it with the
same checks as run_eval.py, and saves it to demo_snapshot/ only if it passes (or --force).

    .venv/bin/python eval/record_snapshot.py [--min-pass 23] [--force]
"""
import argparse
import json
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
sys.path.insert(0, str(Path(__file__).resolve().parent))
import run_eval as E  # noqa: E402

ap = argparse.ArgumentParser()
ap.add_argument("--min-pass", type=int, default=23)
ap.add_argument("--force", action="store_true")
a = ap.parse_args()

d = tempfile.mkdtemp(prefix="kept-snap-")
E.fresh_modules(d)
from kept.seed import seed  # noqa: E402
from kept import agent, learn, snapshot  # noqa: E402

seed(force=True)
out = agent.run_day()
try:
    rules = learn.propose_rules()
except Exception as e:  # the day is already paid for; keep it and say what failed
    rules = f"failed: {type(e).__name__}: {str(e)[:120]}"
g = E.grade(None)
g["checks"]["no_job_failed"] = not {k: v for k, v in out.items() if isinstance(v, str)}
ok = sum(g["checks"].values())
print(json.dumps({"passed": f"{ok}/{len(g['checks'])}", "failed": [k for k, v in g["checks"].items() if not v],
                  "usd": g["usd"], "errors": {k: v for k, v in out.items() if isinstance(v, str)},
                  "rules": rules, "pending": g["pending"], "dishonest": g["dishonest"]}, indent=1, default=str))
if ok >= a.min_pass or a.force:
    print("saved", snapshot.save(Path(d)))
else:
    print("NOT saved; data left in", d)
