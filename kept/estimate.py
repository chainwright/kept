"""Preliminary estimates: from sizes and a material, never from the air.

Alex's price guide in notes.md lists installed prices per unit (per foot of cabinets, per front,
per square foot of countertop or backsplash). Sizes come from the client's own numbers, or, failing
that, from what Nemotron VL estimated in their photo. Code multiplies and adds; the reply shows the
sizes and material it used and says plainly that the real price comes after the measuring visit.
A payment plan, when someone says it's too much, is computed from the same estimate.
"""
from __future__ import annotations

import math
import re

from .store import locked, now_iso, read_json, read_notes, write_json

FILE = "estimates.json"


def guide() -> dict[str, int]:
    """{'cabinets, mid-range painted mdf': 1100, ...} from the '## Price guide' section."""
    sec = read_notes().split("## Price guide")[-1].split("\n## ")[0] if "## Price guide" in read_notes() else ""
    out = {}
    for line in sec.splitlines():
        m = re.match(r"-\s*(.+?):\s*\$([\d,]+)", line.strip())
        if m:
            out[m.group(1).strip().lower()] = int(m.group(2).replace(",", ""))
    return out


def _pick(g: dict, prefix: str, material: str) -> tuple[str, int] | None:
    rows = [(k, v) for k, v in g.items() if k.startswith(prefix)]
    if not rows:
        return None
    mat = (material or "").lower()
    for k, v in rows:
        if mat and any(w in k for w in re.findall(r"[a-z]{3,}", mat)):
            return k, v
    return rows[0]  # the first line in each group is the mid-range default


def _num(x, add_up: bool = False) -> float | None:
    """A size from a model or an email: 12, "12", "about 12 ft", or "8 upper doors, 6 lower doors, 4 drawers"
    (counts add up). Anything else is None, never a crash."""
    if isinstance(x, (int, float)):
        return float(x) if x > 0 else None
    nums = [float(n) for n in re.findall(r"\d+(?:\.\d+)?", str(x or ""))]
    if not nums:
        return None
    v = sum(nums) if add_up else nums[0]
    return v if v > 0 else None


def preliminary(job: str, sizes: dict, material: str = "", counter: str = "", splash: str = "") -> dict | None:
    """Returns {low, high, mid, lines: [...], used: {...}} or None when the sizes it needs are missing."""
    g = guide()
    run, fronts = _num(sizes.get("cabinet_run_ft")), _num(sizes.get("doors_and_drawers"), add_up=True)
    ctop, bsp = _num(sizes.get("countertop_sqft")), _num(sizes.get("backsplash_sqft"))
    lines = []

    def add(label, unit_key, qty, unit_word):
        lines.append({"what": label, "qty": round(qty), "unit": unit_word, "price": g[unit_key],
                      "total": int(round(qty) * g[unit_key]), "basis": unit_key})

    if job == "fronts":
        if not fronts:
            return None
        k, _ = _pick(g, "cabinet fronts", material)
        add(f"New fronts ({k.split(', ')[1]})", k, fronts, "fronts")
    elif job == "countertop":
        if not ctop:
            return None
        k, _ = _pick(g, "countertop", counter or material)
        add(f"Countertop ({k.split(', ')[1]})", k, ctop, "sq ft")
    elif job == "backsplash":
        if not bsp:
            return None
        k, _ = _pick(g, "backsplash", splash or material)
        add(f"Backsplash ({k.split(', ')[1]})", k, bsp, "sq ft")
    elif job == "full_kitchen":
        if not run:
            return None
        k, _ = _pick(g, "cabinets", material)
        add(f"Cabinets ({k.split(', ')[1]})", k, run, "ft of wall")
        if ctop:
            k2, _ = _pick(g, "countertop", counter or "quartz")
            add(f"Countertop ({k2.split(', ')[1]})", k2, ctop, "sq ft")
        if bsp:
            k3, _ = _pick(g, "backsplash", splash or "ceramic")
            add(f"Backsplash ({k3.split(', ')[1]})", k3, bsp, "sq ft")
        for fixed in ("taking out the old kitchen", "sink and faucet hookup"):
            if fixed in g:
                lines.append({"what": fixed.capitalize(), "qty": 1, "unit": "", "price": g[fixed], "total": g[fixed], "basis": fixed})
    else:
        return None
    mid = sum(l["total"] for l in lines)
    low, high = int(math.floor(mid * 0.9 / 100) * 100), int(math.ceil(mid * 1.1 / 100) * 100)
    return {"low": low, "high": high, "mid": mid, "lines": lines,
            "used": {k: _num(sizes.get(k), add_up=(k == "doors_and_drawers")) for k in
                     ("cabinet_run_ft", "doors_and_drawers", "countertop_sqft", "backsplash_sqft")
                     if _num(sizes.get(k), add_up=(k == "doors_and_drawers"))}}


def plan_terms() -> dict | None:
    line = next((l for l in read_notes().splitlines() if "up front" in l.lower() and "monthly" in l.lower()), "")
    m_from = re.search(r"from \$([\d,]+)", line)
    m_pct = re.search(r"(\d+)%\s*up front", line)
    m_n = re.search(r"(\d+)\s+equal monthly", line)
    if not (m_pct and m_n):
        return None
    return {"min": int(m_from.group(1).replace(",", "")) if m_from else 0, "pct": int(m_pct.group(1)), "months": int(m_n.group(1))}


def payment_plan(total: int) -> dict | None:
    t = plan_terms()
    if not t or total < t["min"]:
        return None
    deposit = int(round(total * t["pct"] / 100 / 10) * 10)
    monthly = int(math.ceil((total - deposit) / t["months"] / 5) * 5)
    return {"total": total, "deposit": deposit, "monthly": monthly, "months": t["months"], "pct": t["pct"]}


def remember(addr: str, est: dict, job: str) -> None:
    with locked():
        rows = read_json(FILE, {})
        rows[addr.lower()] = {**est, "job": job, "ts": now_iso()}
        write_json(FILE, rows)


def last_for(addr: str) -> dict | None:
    return read_json(FILE, {}).get(addr.lower())
