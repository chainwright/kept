"""Looking at a client's photo.

People who want a kitchen job priced send a picture of what they have. Nemotron Super VL describes
what a kitchen contractor needs from it: the room, the cabinets and counter, the damage, and what
the photo can't show (which is what the visit is for). It never prices anything; prices come from
Alex's own list, by code.
"""
from __future__ import annotations

import base64
from pathlib import Path

from .agent import _abstain
from .llm import router
from .validators import Verdict, one_of, shape

PROMPT = (
    "A client of a one-person kitchen contractor sent this photo with their email. Describe only what you can "
    "see that matters for the job: what part of the kitchen it shows, cabinets (material, condition), countertop, "
    "hardware (handles, hinges), visible damage, and the style (colour, door type, handle finish) so replacement "
    "parts can match it. Give ROUGH sizes only if the photo shows enough of the kitchen to judge (use standard "
    "cabinet widths and doors as a scale), otherwise null. Say what the photo can't show. Never guess prices. "
    'Reply JSON: {"shows": "one line", "scope": "small_repair|refresh|full_kitchen|unclear", '
    '"seen": ["short facts"], "damage": ["..."], "style": "one line for matching parts", '
    '"rough_sizes": {"cabinet_run_ft": null, "doors_and_drawers": null, "countertop_sqft": null, "backsplash_sqft": null}, '
    '"cant_see": ["..."]}'
)


def describe(path: Path, email_text: str = "") -> dict | None:
    data = base64.b64encode(path.read_bytes()).decode()
    mime = "image/png" if path.suffix.lower() == ".png" else "image/jpeg"
    msgs = [{"role": "user", "content": [
        {"type": "text", "text": PROMPT + (f"\n\nTheir email says: {email_text[:1200]}" if email_text else "")},
        {"type": "image_url", "image_url": {"url": f"data:{mime};base64,{data}"}}]}]
    r = router.ask("see", msgs, purpose=f"look at {path.name}", json_mode=True, max_tokens=700)
    try:
        d = r.json()
    except Exception as e:
        _abstain("photo", path.name, Verdict(False, [f"model reply unusable: {e}"]))
        return None
    v = shape(d, {"shows": str, "scope": str})
    v.merge(one_of(d.get("scope"), ["small_repair", "refresh", "full_kitchen", "unclear"], "scope"))
    if not v:
        _abstain("photo", path.name, v, d)
        return None
    d["model"] = r.model
    return d
