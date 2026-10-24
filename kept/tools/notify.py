"""Reaching the owner on their phone: a Telegram bot with Yes / No buttons.

Optional. Without a bot token the web dashboard is the only place to decide,
which is also how judges and first-time users try Kept.
"""
from __future__ import annotations

import httpx

from ..config import settings
from ..store import append_audit

API = "https://api.telegram.org/bot{token}/{method}"


def enabled() -> bool:
    return bool(settings.telegram_bot_token and settings.telegram_chat_id)


def _call(method: str, **payload) -> dict:
    r = httpx.post(API.format(token=settings.telegram_bot_token, method=method), json=payload, timeout=30)
    r.raise_for_status()
    return r.json()


def tell(text: str) -> None:
    if enabled():
        _call("sendMessage", chat_id=settings.telegram_chat_id, text=text[:4000],
              disable_web_page_preview=True)


def ask(approval: dict) -> None:
    """Send an approval request with two buttons."""
    if not enabled():
        return
    lines = [f"Kept wants to: {approval['summary']}", "", f"Why: {approval['why']}"]
    if approval.get("checks"):
        lines += ["", "Checks passed: " + "; ".join(approval["checks"])]
    _call("sendMessage", chat_id=settings.telegram_chat_id, text="\n".join(lines)[:4000],
          reply_markup={"inline_keyboard": [[
              {"text": "Yes", "callback_data": f"yes:{approval['id']}"},
              {"text": "No", "callback_data": f"no:{approval['id']}"}]]})
    append_audit("notify", id=approval["id"], channel="telegram")


def poll_decisions(offset: int = 0) -> tuple[list[tuple[str, bool]], int]:
    """Returns ([(approval_id, yes)], next_offset). Only the owner's chat counts."""
    if not enabled():
        return [], offset
    res = _call("getUpdates", offset=offset, timeout=0, allowed_updates=["callback_query"])
    out = []
    for u in res.get("result", []):
        offset = max(offset, u["update_id"] + 1)
        cq = u.get("callback_query")
        if not cq or str(cq["message"]["chat"]["id"]) != str(settings.telegram_chat_id):
            continue
        verb, _, aid = cq.get("data", "").partition(":")
        if verb in ("yes", "no") and aid:
            out.append((aid, verb == "yes"))
            _call("answerCallbackQuery", callback_query_id=cq["id"],
                  text="Done" if verb == "yes" else "Cancelled")
    return out, offset
