"""Who is writing? A first look at a new contact, from the web, before Alex replies.

A freelancer who gets an email from a stranger usually spends ten minutes finding out who
they are: is it a real business, where, do they already have a site, what does it lack.
Kept does that with Tavily: it searches for the business the email names and, when the
sender writes from their own domain, reads their current site with Tavily Extract. Nemotron
Super turns the pages into a few facts, and code keeps only facts whose quote is on a page
Tavily returned, from a page that actually names the business. If nothing checks out, Alex
is told that, rather than handed a guess.
"""
from __future__ import annotations

import re

from .agent import _abstain, _msgs, note, read_notes_owner
from .agent import business as owner_business
from .llm import router
from .store import locked, now_iso, read_json, write_json
from .validators import Verdict, grounded, shape, source_id

FILE = "research.json"
FREEMAIL = {"gmail.com", "yahoo.com", "outlook.com", "hotmail.com", "icloud.com", "aol.com", "proton.me",
            "protonmail.com", "gmx.com", "mail.com", "live.com", "me.com"}


def own_domain(addr: str) -> str | None:
    d = addr.split("@")[-1].lower()
    if d in FREEMAIL or d.endswith(".example") or d.endswith("example.com") or "." not in d:
        return None
    return d


def known(addr: str) -> dict | None:
    return read_json(FILE, {}).get(addr.lower())


def look_up(name: str, addr: str, body: str) -> dict:
    from .tools import search

    who = router.ask("classify", _msgs(
        "From this email, name the business the sender runs or represents and its city, only if the email "
        'says so. Reply JSON: {"business": "name or empty", "city": "city or empty", "kind": "e.g. dog grooming or empty"}'
        f"\n\nFrom: {name} <{addr}>\n\n{body[:2000]}"), purpose=f"who is {addr}", json_mode=True, max_tokens=120)
    try:
        b = who.json()
    except Exception:
        b = {}
    business, city = (b.get("business") or "").strip(), (b.get("city") or "").strip()
    # a business counts only if they name it in what they wrote: the model likes to read one into the address
    # ("jo@riverahome" -> "Rivera Home"), and a stranger's shop found that way turned a homeowner into a cafe
    if business and _norm(business)[:14] not in _norm(f"{body} {name}"):
        business = ""
    domain = own_domain(addr)
    out = {"ts": now_iso(), "business": business, "city": city, "kind": (b.get("kind") or "").strip(),
           "domain": domain, "facts": [], "searched": [], "found_site": None}
    if not business and not domain:
        out["note"] = "The email doesn't name a business and comes from a personal address, so there was nothing to look up."
        return _save(addr, out)
    pages = []
    try:
        if domain:
            site = search.extract([f"https://{domain}"])
            out["searched"].append(f"read https://{domain}")
            if site:
                out["found_site"] = site[0]["url"]
                pages += site
        if business:
            q = f'"{business}" {city} {out["kind"]}'.strip()
            out["searched"].append(f"searched: {q}")
            pages += search.search(q, max_results=5, days=None, topic="general", depth="basic")
    except Exception as e:
        _abstain("research", addr, Verdict(False, [f"web lookup failed: {e}"]))
        out["note"] = "The web lookup failed, so Kept isn't guessing."
        return _save(addr, out)
    # a page only counts if it names the business (or is their own site)
    key = _norm(business)[:14]
    out["pages_seen"] = len(pages)
    pages = [p for p in pages if (domain and domain in p["url"]) or (key and key in _norm(p["content"]))]
    out["pages_used"] = [p["url"] for p in pages][:6]
    if not pages:
        out["note"] = f"Nothing on the web clearly about {business or domain}. Could be brand new, or not what it says."
        return _save(addr, out)
    sources = {p["id"]: p["content"] for p in pages}
    listing = "\n\n".join(f"[{p['id']}] {p['url']}\n{excerpt(p['content'], key)}" for p in pages[:6])
    r = router.ask("plan", _msgs(
        f"{read_notes_owner()} runs {owner_business()} and just got an email from {name} "
        f"({business or domain}). From these pages, give up to 4 short facts that help {read_notes_owner()} reply "
        f"well: what the business is and where, how established it looks (opening date, size, reviews), and "
        f"anything that bears on {note('What new clients need', 'the work they might need')}. "
        "Each fact must quote exact words from its page. "
        'Reply JSON: {"facts": [{"text": "...", "source": "<id>", "quote": "exact words"}]}\n\n' + listing),
        purpose=f"research {addr}", json_mode=True, max_tokens=700)
    try:
        facts = r.json().get("facts") or []
    except Exception as e:
        _abstain("research", addr, Verdict(False, [f"model reply unusable: {e}"]))
        return _save(addr, out)
    for f in facts[:4]:
        f["source"] = source_id(f.get("source"), sources)
        v = shape(f, {"text": str, "quote": str})
        if v:
            v.merge(grounded([f], sources))
        if not v:
            _abstain("research", f.get("text", addr)[:60], v, f)
            out.setdefault("dropped", []).append({"text": str(f.get("text", ""))[:160], "why": "; ".join(v.problems)[:200]})
            continue
        url = next(p["url"] for p in pages if p["id"] == f["source"])
        out["facts"].append({"text": f["text"], "quote": f["quote"], "url": url})
    if not out["facts"]:
        out["note"] = "Found pages, but no fact survived the quote check."
    return _save(addr, out)


def _norm(s: str) -> str:
    """Lowercase with curly quotes made straight; same length, so positions still match the page."""
    return s.lower().translate(str.maketrans("\u2019\u2018\u201c\u201d", "''\"\""))


def excerpt(text: str, key: str, size: int = 3000) -> str:
    """The part of a page that is about the business. A page usually opens with menus and
    cookie banners; the business may be named thousands of characters further down."""
    low = _norm(text)
    hits = [m.start() for m in re.finditer(re.escape(key), low)] if key else []
    if not hits:
        return text[:size]
    parts, used, end = [], 0, -1
    for h in hits:
        a, b = max(h - 600, end + 1), min(len(text), h + 1200)
        if a >= b:
            continue
        piece = text[a:b][: size - used]
        parts.append(piece); used += len(piece); end = b
        if used >= size:
            break
    return "\n…\n".join(parts)


def _save(addr: str, out: dict) -> dict:
    with locked():
        rows = read_json(FILE, {})
        rows[addr.lower()] = out
        write_json(FILE, rows)
    return out
