"""Dashboard + JSON API. Run: uvicorn kept.web:app --port 8000"""
from __future__ import annotations

import threading
import time
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from . import agent, approvals, calibration, learn, ledger, memory_qa, precheck
from .config import ROOT, TIERS, settings
from .llm import ROUTES, router
from .store import read_audit, read_json
from .tools import mail, notify  # noqa: F401  (registers actions)

WEB = ROOT / "web"
JOBS = {"triage": agent.triage_inbox, "follow_ups": agent.follow_ups, "watch": agent.watch_topics,
        "overload": agent.weigh_overload, "brief": agent.morning_brief, "day": agent.run_day,
        "learn": learn.propose_rules}
_busy = threading.Lock()


def _telegram_loop() -> None:
    offset = 0
    while True:
        try:
            decisions, offset = notify.poll_decisions(offset)
            for aid, yes in decisions:
                try:
                    approvals.decide(aid, yes, by="owner (phone)")
                except approvals.GateError:
                    pass
        except Exception:
            time.sleep(10)
        time.sleep(3)


@asynccontextmanager
async def lifespan(app: FastAPI):
    from .scheduler import start
    from .seed import seed

    if settings.demo:
        seed()
    start()
    if notify.enabled():
        threading.Thread(target=_telegram_loop, daemon=True).start()
    yield


app = FastAPI(title="Kept", lifespan=lifespan)
if (WEB / "static").exists():
    app.mount("/static", StaticFiles(directory=WEB / "static"), name="static")


@app.get("/")
def index():
    return FileResponse(WEB / "index.html")


@app.get("/api/state")
def state():
    audit = read_audit(400)
    calls = [a for a in audit if a["kind"] == "llm"]
    return {
        "owner": settings.owner_name, "demo": settings.demo,
        "brief": read_json("brief.json", None),
        "open": ledger.open_sorted(),
        "closed": [r for r in ledger.items() if r["status"] != "open"][-15:][::-1],
        "pending": approvals.pending(),
        "decided": [a for a in approvals.recent(40) if a["status"] != "pending"][:15],
        "abstained": read_json("abstained.json", [])[-15:][::-1],
        "watch": read_json("watch.json", None),
        "labels": read_json("labels.json", {}),
        "inbox": mail.inbox(30),
        "calls": calls[-40:][::-1],
        "spend_today": round(router.spent_today(), 4),
        "budget": settings.daily_budget_usd,
        "tiers": {k: {"model": router._resolved.get(k, t.default_model), "why": t.why,
                      "in": t.usd_in_per_m, "out": t.usd_out_per_m} for k, t in TIERS.items()},
        "routes": ROUTES,
        "activity": [a for a in audit if a["kind"] not in ("llm",)][-40:][::-1],
        "busy": _busy.locked(),
        "calibration": calibration.as_json(),
    }


@app.post("/api/approvals/{aid}/{verdict}")
def decide(aid: str, verdict: str):
    if verdict not in ("yes", "no"):
        raise HTTPException(400, "yes or no")
    try:
        return approvals.decide(aid, verdict == "yes", by="owner (web)")
    except approvals.GateError as e:
        raise HTTPException(409, str(e))


class NewItem(BaseModel):
    text: str
    who: str = ""
    due: str | None = None
    direction: str = "i_owe"


@app.post("/api/ledger")
def add_item(item: NewItem):
    try:
        return ledger.add(item.text, who=item.who, due=item.due or None, origin="owner",
                          direction=item.direction)
    except ledger.LedgerError as e:
        raise HTTPException(400, str(e))


class Close(BaseModel):
    resolution: str
    note: str


@app.post("/api/ledger/{item_id}/close")
def close_item(item_id: str, body: Close):
    try:
        return ledger.close(item_id, body.resolution, body.note)
    except ledger.LedgerError as e:
        raise HTTPException(400, str(e))


@app.post("/api/run/{job}")
def run(job: str):
    if job not in JOBS:
        raise HTTPException(404, f"jobs: {sorted(JOBS)}")
    if not _busy.acquire(blocking=False):
        raise HTTPException(409, "Kept is already working on something")
    try:
        return {"job": job, "result": JOBS[job]()}
    finally:
        _busy.release()


class Question(BaseModel):
    question: str


class Draft(BaseModel):
    text: str
    to: str = ""


@app.post("/api/precheck")
def before_you_send(d: Draft):
    return precheck.check(d.text, d.to)


@app.post("/api/ask")
def ask(q: Question):
    return memory_qa.ask(q.question[:500])


@app.post("/api/demo/reset")
def reset_demo():
    if not settings.demo:
        raise HTTPException(403, "only in demo mode")
    from .seed import seed

    seed(force=True)
    return {"ok": True}
