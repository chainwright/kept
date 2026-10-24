"""The approval gate: anything that leaves the machine, costs money, or can't be
undone waits for the owner's Yes.

The gate lives in code, not in a prompt. An action handler is only reachable
through `execute`, and `execute` refuses anything that is not approved. A model
can propose whatever it likes; it has no path to run it.
"""
from __future__ import annotations

import uuid
from typing import Any, Callable

from .store import append_audit, journal, now_iso, read_json, write_json

FILE = "approvals.json"

# kind -> (handler, needs_approval). Read-only things don't bother the owner.
_ACTIONS: dict[str, tuple[Callable[[dict], Any], bool]] = {}


class GateError(PermissionError):
    pass


def action(kind: str, *, needs_approval: bool = True):
    def deco(fn: Callable[[dict], Any]):
        _ACTIONS[kind] = (fn, needs_approval)
        return fn
    return deco


def kinds() -> dict[str, bool]:
    return {k: v[1] for k, v in _ACTIONS.items()}


def _all() -> list[dict]:
    return read_json(FILE, [])


def pending() -> list[dict]:
    return [a for a in _all() if a["status"] == "pending"]


def recent(n: int = 30) -> list[dict]:
    return _all()[-n:][::-1]


def get(aid: str) -> dict:
    for a in _all():
        if a["id"] == aid:
            return a
    raise GateError(f"no approval {aid}")


def propose(kind: str, args: dict, *, summary: str, why: str, checks: list[str] | None = None,
            ledger_id: str | None = None, reasoning: str = "", model_label: str = "") -> dict | None:
    """Queue an action. Returns the request (nothing has happened yet), or None if another
    message to the same person is already waiting for the owner."""
    if kind not in _ACTIONS:
        raise GateError(f"unknown action '{kind}'")
    rows = _all()
    # don't nag twice about the same thing
    for a in rows:
        if a["status"] == "pending" and a["kind"] == kind and a["args"] == args:
            return a
    # one message to a person at a time: in a live run three different jobs queued three
    # emails to the same client, and two of them contradicted each other
    if kind == "send_email":
        for a in rows:
            if a["status"] == "pending" and a["kind"] == "send_email" and \
                    a["args"].get("to", "").lower() == str(args.get("to", "")).lower():
                append_audit("approval_skipped", action=kind, to=args.get("to"), waiting=a["id"])
                journal(f"Held a second message to {args.get('to')}: '{a['summary']}' is still waiting for you")
                return None
    req = {"id": uuid.uuid4().hex[:8], "kind": kind, "args": args, "summary": summary, "why": why,
           "checks": checks or [], "ledger_id": ledger_id, "reasoning": reasoning[:4000],
           "model_label": model_label, "status": "pending", "created": now_iso()}
    rows.append(req)
    write_json(FILE, rows)
    append_audit("approval_requested", id=req["id"], action=kind, summary=summary)
    journal(f"Asked the owner: {summary} [{req['id']}]")
    return req


def decide(aid: str, yes: bool, *, by: str = "owner") -> dict:
    rows = _all()
    for a in rows:
        if a["id"] == aid:
            if a["status"] != "pending":
                raise GateError(f"{aid} was already {a['status']}")
            a["status"] = "approved" if yes else "rejected"
            a["decided"] = now_iso()
            a["by"] = by
            write_json(FILE, rows)
            append_audit("approval_decided", id=aid, yes=yes, by=by)
            journal(f"Owner said {'Yes' if yes else 'No'} to: {a['summary']}")
            if yes:
                return execute(aid)
            return a
    raise GateError(f"no approval {aid}")


def execute(aid: str) -> dict:
    rows = _all()
    for a in rows:
        if a["id"] != aid:
            continue
        handler, needs = _ACTIONS[a["kind"]]
        if needs and a["status"] != "approved":
            append_audit("gate_blocked", id=aid, action=a["kind"], status=a["status"])
            raise GateError(f"'{a['kind']}' needs the owner's Yes; status is {a['status']}")
        try:
            result = handler(a["args"])
            a["status"], a["result"] = "done", result
        except Exception as e:  # the owner should see failures, not silence
            a["status"], a["result"] = "failed", f"{type(e).__name__}: {e}"
        a["finished"] = now_iso()
        write_json(FILE, rows)
        append_audit("action", id=aid, action=a["kind"], status=a["status"], result=str(a["result"])[:300])
        journal(f"{a['kind']} {a['status']}: {a['summary']}")
        return a
    raise GateError(f"no approval {aid}")


def run_unguarded(kind: str, args: dict) -> Any:
    """For read-only actions only. Anything registered as needing approval is refused."""
    handler, needs = _ACTIONS[kind]
    if needs:
        append_audit("gate_blocked", action=kind, reason="unguarded call to a guarded action")
        raise GateError(f"'{kind}' can only run after approval")
    return handler(args)
