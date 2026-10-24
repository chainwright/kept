"""Before you send: catch the promise you're about to make, and make it one you'll keep.

Paste a reply you're about to send. Kept finds every promise in it (Nemotron Nano),
checks each date against your own track record (plain code, see calibration.py) and
against what's already due that day, and if your history says you'll be late, offers a
rewrite of just that sentence (Nemotron Super). Code then checks the rewrite changed the
date and nothing else that matters.
"""
from __future__ import annotations

import re
from datetime import date, datetime

from . import calibration, ledger
from .agent import _abstain, _msgs, read_notes_owner
from .llm import router
from .validators import Verdict, grounded, plausible_due, resolve_when, shape


def _load_on(day: str) -> list[dict]:
    return [r for r in ledger.open_sorted(which="i_owe") if (r.get("due") or "")[:10] == day]


def check(draft: str, to_name: str = "") -> dict:
    today = date.today()
    owner = read_notes_owner()
    draft = draft.strip()[:4000]
    if not draft:
        return {"promises": [], "note": "Nothing to check."}
    r = router.ask("spot", _msgs(
        f"{owner} is about to send this message{(' to ' + to_name) if to_name else ''}. List every promise "
        f"{owner} makes in it (things they say they will do, with or without a date). For each give a short "
        "description, the due date as YYYY-MM-DD if a day is named or implied (resolve 'Friday', 'tomorrow', "
        "'end of the week' against today's date), the exact words that name the time ('by Friday'), and the "
        "exact sentence. Reply JSON: "
        '{"promises": [{"text": "...", "due": "YYYY-MM-DD or null", "when_words": "...", "quote": "exact words"}]}\n'
        f"Today is {today.isoformat()} ({today:%A}).\n\nMessage:\n{draft}", "extract"),
        purpose="before-you-send: find promises", json_mode=True, max_tokens=500)
    try:
        found = r.json().get("promises") or []
    except Exception as e:
        _abstain("precheck", draft[:60], Verdict(False, [f"model reply unusable: {e}"]))
        return {"promises": [], "note": "Couldn't read the promises in this draft, so Kept isn't guessing."}
    out = []
    for p in found[:5]:
        v = shape(p, {"text": str, "quote": str})
        if v:
            # Nano sometimes quotes only the time words ("by Friday"); the promise text itself is a
            # fine quote when it appears verbatim in the draft. Either way the words must be there.
            tries = [p["quote"], p["text"]]
            ok = next((q for q in tries if grounded([{"source": "draft", "quote": q}], {"draft": draft})), None)
            if ok:
                p["quote"] = ok
            v.merge(grounded([{"source": "draft", "quote": p["quote"]}], {"draft": draft}))
            v.merge(plausible_due(p.get("due")))
        if not v:
            _abstain("precheck", str(p)[:60], v, p)
            continue
        item = {"text": p["text"], "quote": p["quote"], "due": p.get("due"), "when_words": p.get("when_words") or ""}
        code_due = resolve_when(item["when_words"], today)
        if code_due and code_due.isoformat() != (item["due"] or "")[:10]:
            # the words win over the model's arithmetic
            item["model_due"], item["due"] = item["due"], code_due.isoformat()
        if item["due"]:
            item["advice"] = calibration.realistic_due(p["text"], item["due"])
            busy = _load_on(item["due"][:10])
            if busy:
                item["same_day"] = [b["text"] for b in busy]
        out.append(item)
    result = {"promises": out, "model": r.model}
    late = [p for p in out if p.get("advice") and p["when_words"] and p["when_words"].lower() in draft.lower()]
    if late:
        result["rewrite"] = _rewrite(draft, late)
    return result


def _weekday_words(iso: str) -> list[str]:
    d = datetime.fromisoformat(iso).date()
    return [d.strftime("%A").lower(), d.strftime("%B %-d").lower(), d.strftime("%b %-d").lower(), iso]


def _rewrite(draft: str, late: list[dict]) -> dict:
    changes = "\n".join(f"- change '{p['when_words']}' so the promise lands on "
                        f"{datetime.fromisoformat(p['advice']['suggested']).date():%A, %B %-d}" for p in late)
    r = router.ask("draft", _msgs(
        "Rewrite this message changing ONLY the time words listed below. Keep every other word, the tone and "
        "the length. Write the new day the way people do ('Monday', 'Tuesday the 10th'), not as YYYY-MM-DD. "
        'Reply JSON: {"text": "..."}\n\nChanges:\n' + changes + "\n\nMessage:\n" + draft, "follow_up"),
        purpose="before-you-send: realistic dates", json_mode=True, max_tokens=900)
    try:
        new = r.json().get("text", "")
    except Exception as e:
        return {"ok": False, "problems": [f"model reply unusable: {e}"]}
    v = Verdict(True)
    if not new.strip() or new.strip() == draft.strip():
        v.add("the rewrite didn't change anything")
    ratio = len(new) / max(1, len(draft))
    if not 0.7 <= ratio <= 1.4:
        v.add(f"the rewrite changed the length too much ({ratio:.0%} of the original)")
    for p in late:
        if not any(w in new.lower() for w in _weekday_words(p["advice"]["suggested"])):
            v.add(f"the rewrite doesn't name the new day for '{p['text']}'")
        if p["when_words"].lower() in new.lower():
            v.add(f"the rewrite still says '{p['when_words']}'")
    # every sentence without the date should survive (allowing small edits)
    keep = [s.strip() for s in re.split(r"(?<=[.!?])\s+", draft)
            if s.strip() and not any(p["when_words"].lower() in s.lower() for p in late)]
    lost = [s for s in keep if len(s) > 25 and s[:25].lower() not in new.lower()]
    if lost:
        v.add(f"the rewrite dropped or reworded other sentences, e.g. '{lost[0][:60]}'")
    return {"ok": v.ok, "text": new if v.ok else "", "problems": v.problems, "model": r.model}
