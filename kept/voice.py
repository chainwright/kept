"""Hands busy: Alex talks to Kept and Kept talks back.

Alex is up a stepladder with a drill in one hand. The browser turns his words into text
and reads Kept's answers aloud; this module decides what the words mean.

The rule that matters: a model never decides that Alex said Yes. Whether a spoken answer
is a Yes or a No is read by plain code from the words themselves, and anything unclear
(a "yes, but", a "no" and a "send" together, mumbling) sends nothing and asks again.
A spoken No only holds the draft; nothing is thrown away by voice.
Questions about his week go to the same checked answers as typing does (memory_qa);
an answer whose quotes don't check out is not read out as fact.
"""
from __future__ import annotations

import re
from datetime import date

from . import approvals, memory_qa
from .store import append_audit, read_json

_YES = re.compile(r"\b(yes|yeah|yep|yup|sure|ok|okay|go ahead|send it|send that|send|do it|approve|approved|"
                  r"sounds good|perfect|correct|please do)\b")
_NO = re.compile(r"\b(no|nope|not|don't|dont|do not|wait|hold|stop|cancel|later|never mind|nevermind|skip|"
                 r"decline|change|edit|but|instead|hang on)\b")
_BRIEF = re.compile(r"\b(my (?:morning|day|plan)|plan for today|today'?s plan|brief me|morning brief|"
                    r"what(?:'s| is| do i have)? (?:on )?(?:for )?today|how(?:'s| is) (?:my )?(?:day|today))\b")
_NEXT = re.compile(r"\b(next|what'?s waiting|what is waiting|anything (?:else|new|waiting)|needs my yes|pending|"
                   r"approve|approval|sign off|my ok|my okay)\b")
_AGAIN = re.compile(r"\b(read (?:it|that|me)|again|repeat|say that)\b")


def verdict(said: str) -> str:
    """'yes', 'no' or 'unclear', from the words alone. Unclear is never treated as Yes."""
    s = " " + re.sub(r"[^a-z' ]+", " ", (said or "").lower().replace("’", "'")) + " "
    yes, no = bool(_YES.search(s)), bool(_NO.search(s))
    if yes and not no:
        return "yes"
    if no and not yes:
        return "no"
    return "unclear"


def _first(addr: str) -> str:
    """'maria@lopezhome.example' -> 'Maria', for 'Sent to Maria'."""
    from .tools import mail
    for m in mail.inbox(60):
        if addr and addr.lower() in m["from"].lower():
            return m["from"].split("<")[0].strip().split(" ")[0] or addr
    return addr.split("@")[0].split(".")[0].capitalize() if addr else "them"


def spoken(a: dict) -> str:
    """One waiting item, as Kept would say it out loud."""
    if a["kind"] == "send_email":
        who = _first(a["args"].get("to", ""))
        body = re.sub(r"\s*\n\s*", " ", a["args"].get("body", "").strip())
        if body and body[-1] not in ".!?":
            body += "."   # the sign-off ('Alex') shouldn't run into the question
        return f"{a['summary'].rstrip('.')}. Here is the email to {who}: {body} Shall I send it?"
    return f"{a['summary']}. {a.get('why', '')} Shall I go ahead?"


def speakable(text: str) -> str:
    """Written forms read badly aloud: '2026-11-01' -> 'Sunday, November 1', '#118' -> 'number 118'."""
    def day(m):
        try:
            return date.fromisoformat(m.group(0)).strftime("%A, %B %-d")
        except ValueError:
            return m.group(0)
    text = re.sub(r"\b20\d\d-\d\d-\d\d\b", day, text or "")
    return re.sub(r"#\s?(\d+)", r"number \1", text)


def handle(said: str, pending_id: str | None = None) -> dict:
    out = _handle(said, pending_id)
    out["say"] = speakable(out.get("say", ""))
    return out


def _handle(said: str, pending_id: str | None = None) -> dict:
    said = (said or "").strip()[:400]
    out: dict = {"heard": said}
    if not said:
        return {**out, "say": "I didn't catch that."}
    append_audit("voice", heard=said, pending=pending_id)
    low = said.lower()
    if pending_id:
        try:
            a = approvals.get(pending_id)
        except approvals.GateError:
            a = None
        if a and a["status"] != "pending":
            a = None  # already decided: treat what was said as a fresh request
        if a and (_AGAIN.search(low) or (_NEXT.search(low) and not re.search(r"\bnext\b", low))):
            return {**out, "pending_id": a["id"], "say": spoken(a)}
        v = verdict(said) if a and not question(said) else "unclear"
        if a and v == "yes":
            done = approvals.decide(pending_id, True, by="owner (voice)")
            who = _first(a["args"].get("to", "")) if a["kind"] == "send_email" else ""
            ok = done.get("status") == "done"
            return {**out, "decided": "yes", "approval": done,
                    "say": (f"Sent to {who}." if who else "Done.") if ok else f"I tried, but it failed: {done.get('result')}"}
        if a and v == "no":
            # a spoken no only holds the draft ("hold on" isn't "throw it away"); it stays on screen
            append_audit("voice_held", id=pending_id)
            return {**out, "decided": "held", "say": "Okay, I'm holding it. Nothing was sent."}
        answered = bool(_YES.search(f" {low} ") or _NO.search(f" {low} "))   # a yes/no word, but mixed
        if a and answered and not question(said) and not _BRIEF.search(low) and not _NEXT.search(low):
            return {**out, "pending_id": a["id"], "say": "I didn't send it. Say yes to send it, or no to hold it."}
    if _BRIEF.search(low):
        b = read_json("brief.json", None)
        if b and b.get("plan"):
            lines = [p["text"] for p in b["plan"]][:3]
            gap = next((l["text"] for l in b.get("lines", []) if "short" in l["text"].lower()), "")
            return {**out, "say": "Today: " + " ".join(lines) + (f" And: {gap}" if gap else "")}
    if _NEXT.search(low) and (not question(said) or re.search(r"waiting|needs my yes|pending|approv|sign off", low)):
        waiting = [w for w in approvals.pending() if w["id"] != pending_id] or approvals.pending()
        if not waiting:
            return {**out, "say": "Nothing is waiting for you."}
        a = waiting[0]
        return {**out, "pending_id": a["id"], "say": spoken(a), "left": len(approvals.pending())}
    kind = "question" if question(said) and not _HELLO.match(low) else intent(said)
    if kind == "brief":
        return _handle("what's my plan for today", None) | {"heard": said}
    if kind == "waiting":
        return _handle("what's waiting", pending_id) | {"heard": said}
    if re.match(r"(thanks|thank you|cheers|great|perfect|cool)\b", low) and not question(said):
        return {**out, "say": "Anytime."}
    if kind != "question":
        hi = "Hi Alex. " if _HELLO.match(low) else ""
        return {**out, "say": hi + HELP}
    ans = memory_qa.ask(said)
    if ans.get("verified"):
        return {**out, "say": ans["answer"], "evidence": ans.get("evidence", []), "model": ans.get("model")}
    return {**out, "say": "I couldn't find that in your records, so I won't guess.", "problems": ans.get("problems")}


HELP = ("I can read you what's waiting for your yes, tell you your plan for today, "
        "or answer questions about your clients and money. What do you need?")
_HELLO = re.compile(r"(hi|hello|hey|good (morning|afternoon|evening)|kept|alex)\b")


def intent(said: str) -> str:
    """Free speech that matched no fixed phrase: Nemotron Nano sorts it. It only picks what to
    read out; it can never approve anything (that path above is code only)."""
    from .agent import _msgs
    from .llm import router
    try:
        r = router.ask("classify", _msgs(
            "Alex, a kitchen contractor, said this to his assistant out loud. What does he want? "
            'Reply JSON: {"intent": "brief" (his plan or schedule for today), "waiting" (drafts or messages '
            'waiting for his approval), "question" (a question about his clients, promises, invoices or money), '
            'or "other" (a greeting, small talk, or unclear)}\n\n' + f'He said: "{said}"'),
            purpose="voice intent", json_mode=True, max_tokens=40)
        k = str(r.json().get("intent", "")).strip().lower()
    except Exception:
        k = ""
    return k if k in ("brief", "waiting", "question", "other") else ("question" if question(said) else "other")


def question(said: str) -> bool:
    """A real question ('who owes me money?') rather than an answer or a command."""
    s = said.lower().strip()
    return s.endswith("?") or bool(re.match(r"(who|what|when|how|which|did|do i|have i|is|are|does)\b", s))
