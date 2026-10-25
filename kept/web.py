"""Dashboard + JSON API. Run: uvicorn kept.web:app --port 8000"""
from __future__ import annotations

import threading
import time
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, File, HTTPException, UploadFile
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from . import agent, approvals, calibration, checkins, followups, growth, learn, ledger, media, memory_qa, money, offers, precheck, rescue, scope
from .config import ROOT, TIERS, settings
from .llm import ROUTES, BudgetExceeded, router
from .store import read_audit, read_json
from .tools import mail, notify  # noqa: F401  (registers actions)

WEB = ROOT / "web"
JOBS = {"triage": agent.triage_inbox, "follow_ups": agent.follow_ups, "watch": agent.watch_topics,
        "overload": agent.weigh_overload, "brief": agent.morning_brief, "day": agent.run_day,
        "learn": learn.propose_rules, "money": money.chase, "rescue": rescue.plan,
        "offers": offers.propose, "growth": growth.moments, "checkins": checkins.propose, "quiet_leads": followups.propose}
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


def data_dir_has_state() -> bool:
    from .store import data_dir
    return (data_dir() / "inbox.json").exists()


@asynccontextmanager
async def lifespan(app: FastAPI):
    from .scheduler import start
    from .seed import seed

    if settings.demo:
        from . import snapshot
        if snapshot.available() and not (data_dir_has_state()):
            snapshot.restore()
        else:
            seed()
    start()
    if notify.enabled():
        threading.Thread(target=_telegram_loop, daemon=True).start()
    yield


app = FastAPI(title="Kept", lifespan=lifespan)
if (WEB / "static").exists():
    app.mount("/static", StaticFiles(directory=WEB / "static"), name="static")


@app.get("/api/health")
def health():
    """Tiny wake-up probe for the landing page on another domain."""
    from fastapi.responses import JSONResponse
    return JSONResponse({"ok": True}, headers={"Access-Control-Allow-Origin": "*", "Cache-Control": "no-store"})


_BUILD = str(int(time.time()))


def _page(name: str):
    """Pages name their scripts and styles with this build's stamp, so a redeploy never meets a stale cache."""
    from fastapi.responses import HTMLResponse
    html = (WEB / name).read_text()
    for asset in ("app.js", "app.css", "both.js", "both.css", "site.css"):
        html = html.replace(f'/static/{asset}"', f'/static/{asset}?v={_BUILD}"')
    return HTMLResponse(html, headers={"Cache-Control": "no-cache"})


@app.get("/")
def index():
    """Both sides: the client writing on the left, Alex with Kept on the right."""
    return _page("both.html")


@app.get("/dashboard")
def dashboard():
    """Alex's full dashboard."""
    return _page("index.html")


@app.get("/api/state")
def state():
    audit = read_audit(400)
    calls = [a for a in audit if a["kind"] == "llm"]
    return {
        "owner": settings.owner_name, "demo": settings.demo, "snapshot": _snapshot_meta(),
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
        "cash": money.forecast(30),
        "invoices": money.load()["invoices"],
        "habits": {c: money.payment_habit(c) for c in {i["client"] for i in money.load()["invoices"]}},
        "scope": read_json("scope.json", [])[-10:][::-1],
        "rescue": read_json("rescue.json", None),
        "offers_plan": read_json("offers_plan.json", None),
        "growth": read_json("growth_last.json", None),
        "media": read_json("media.json", {}),
        "calendar": _upcoming(),
        "checkins": read_json("checkins_last.json", None),
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


def _upcoming():
    from . import schedule
    return schedule.upcoming(14)


@app.get("/demo_media/{name}")
def demo_photo(name: str):
    """Sample photos a visitor can attach to their email in one click."""
    p = (ROOT / "demo_media" / name).resolve()
    if p.parent != (ROOT / "demo_media").resolve() or not p.exists():
        raise HTTPException(404)
    return FileResponse(p)


def _snapshot_meta():
    from . import snapshot
    return snapshot.meta() if settings.demo else None


@app.post("/api/run/{job}")
def run(job: str):
    if job not in JOBS:
        raise HTTPException(404, f"jobs: {sorted(JOBS)}")
    if not _busy.acquire(blocking=False):
        raise HTTPException(409, "Kept is already working on something")
    try:
        if settings.demo and job == "day" and _snapshot_meta():
            # the recorded morning has already read this inbox; a live run starts from the fresh week
            from .seed import seed
            seed(force=True)
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


class Spoken(BaseModel):
    said: str
    pending_id: str | None = None


@app.post("/api/voice")
def voice_turn(v: Spoken):
    """One spoken turn. The browser does speech-to-text and reads the answer aloud."""
    from . import voice
    try:
        return voice.handle(v.said, v.pending_id)
    except approvals.GateError as e:
        raise HTTPException(409, str(e))
    except BudgetExceeded as e:
        raise HTTPException(429, f"{e}. The demo has a small daily model budget; try again tomorrow.")


@app.post("/api/ask")
def ask(q: Question):
    return memory_qa.ask(q.question[:500])


@app.get("/media/{client}/{name}")
def media_file(client: str, name: str):
    from .store import data_dir
    p = (data_dir() / "media" / client / name).resolve()
    if not str(p).startswith(str((data_dir() / "media").resolve())) or not p.exists():
        raise HTTPException(404)
    return FileResponse(p)


@app.post("/api/media/{client}/{which}")
async def upload_photo(client: str, which: str, file: UploadFile = File(...)):
    if which not in ("before", "after"):
        raise HTTPException(400, "before or after")
    try:
        return media.save_upload(client, which, file.filename or "photo.jpg", await file.read())
    except ValueError as e:
        raise HTTPException(400, str(e))


class Letter(BaseModel):
    who: str = "maria"
    subject: str = ""
    body: str
    name: str = ""
    email: str = ""
    image: str = ""  # optional photo as a data: URL


@app.get("/api/next_visit")
def next_visit():
    """The first free measuring time in Alex's calendar, for the 'Next free visit' badge on Alex's site."""
    from . import schedule
    slots = schedule.free_slots(1)
    return {"label": slots[0]["label"] if slots else None}


@app.get("/api/people")
def people(mine: str = ""):
    """Alex's demo clients, plus only the new contacts this visitor wrote as (their browser passes them):
    another visitor's name and email never show up in someone else's list."""
    from . import tryit
    own = {e.strip().lower() for e in mine.split(",") if e.strip()}
    return [p for p in tryit.client_base() if p["key"] != "new" or p["email"].lower() in own]


@app.get("/api/thread")
def get_thread(email: str):
    from .reply import thread
    return thread(email)


@app.post("/api/demo/mail")
def write_to_alex(l: Letter):
    """A visitor's own email, handled live on Nemotron (demo only; nothing is ever sent)."""
    if not settings.demo:
        raise HTTPException(403, "only in demo mode")
    from . import tryit
    # another visitor's email may be in progress: wait our turn rather than turn this one away
    if not _busy.acquire(timeout=150):
        raise HTTPException(409, "Kept is busy with other emails right now; try again in a minute")
    try:
        return tryit.handle(l.who, l.subject, l.body, l.name, l.email, l.image)
    except BudgetExceeded as e:
        raise HTTPException(429, f"{e}. The demo has a small daily model budget; try again tomorrow.")
    except ValueError as e:
        raise HTTPException(400, str(e))
    finally:
        _busy.release()


@app.post("/api/demo/reset")
def reset_demo(fresh: bool = False):
    """Back to the recorded morning (default) or, with ?fresh=1, the untouched week before any run."""
    if not settings.demo:
        raise HTTPException(403, "only in demo mode")
    from . import snapshot
    from .seed import seed

    if snapshot.available() and not fresh:
        return {"ok": True, "snapshot": snapshot.restore()}
    seed(force=True)
    return {"ok": True}
