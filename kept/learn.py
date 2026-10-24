"""Kept writes its own rulebook from your history, with your Yes.

Once a week Nemotron Ultra reads every promise you closed and looks for a pattern
in where you slip (a kind of work, a weekday, a type of client). It proposes a rule
and points at the exact ledger rows behind it. Code recomputes the numbers from those
rows; a rule whose evidence doesn't actually show a pattern is held back. An accepted
rule is appended to a skill file, and every later prompt that uses that skill follows it.
"""
from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path

from . import approvals, calibration, ledger
from .agent import SKILLS, _abstain, _msgs, read_notes_owner, skill
from .llm import router
from .store import journal, now_iso
from .validators import Verdict, sendable_text, shape

SKILL_TARGETS = ("follow_up", "extract", "brief")
MIN_EVIDENCE = 4
MIN_LATE_SHARE = 0.6


def _history() -> list[dict]:
    rows = []
    for r in ledger.items():
        s = calibration.slip_days(r)
        if s is None:
            continue
        rows.append({"id": r["id"], "text": r["text"], "who": r.get("who", ""),
                     "kind": calibration.kind_of(r["text"]),
                     "due_weekday": datetime.fromisoformat(r["due"][:10]).strftime("%A"),
                     "days_late": s})
    return rows


PATTERN_KEYS = ("kind", "due_weekday", "who")


def matching(pattern: dict, history: list[dict]) -> list[dict]:
    """Every row that fits the pattern, chosen by code. In a live run Ultra cited only the late
    rows of a pattern ("5 of 5") and left out the one that was on time; this can't."""
    def norm(k, v):
        v = str(v).strip().lower()
        if k == "due_weekday":  # "due Friday", "Fridays" -> "friday"
            v = next((d for d in WEEKDAYS if d in v), v)
        return v
    keys = {k: norm(k, v) for k, v in pattern.items() if k in PATTERN_KEYS and v}
    return [h for h in history if keys and all(str(h[k]).lower() == v for k, v in keys.items())]


WEEKDAYS = ["monday", "tuesday", "wednesday", "thursday", "friday", "saturday", "sunday"]


def moves_earlier(rule_text: str, pattern: dict) -> bool:
    """A rule for promises that land late must not tell you to promise an earlier day."""
    base = next((d for d in WEEKDAYS if d in str(pattern.get("due_weekday", "")).lower()), None)
    if not base:
        return False
    named = [d for d in WEEKDAYS if d in rule_text.lower() and d != base]
    return bool(named) and all(WEEKDAYS.index(d) < WEEKDAYS.index(base) for d in named)


def evidence_stats(rows: list[dict]) -> dict:
    late = [h for h in rows if h["days_late"] > 0]
    return {"n": len(rows), "late": len(late),
            "share_late": round(len(late) / len(rows), 2) if rows else 0.0,
            "typical_days_late": sorted(h["days_late"] for h in late)[len(late) // 2] if late else 0}


def propose_rules() -> list[dict]:
    history = _history()
    if len(history) < MIN_EVIDENCE * 2:
        journal("Not enough closed promises yet to learn anything about you")
        return []
    late_kinds = {k: v for k, v in calibration.as_json()["by_kind"].items() if v["median_slip"] > 0}
    table = "\n".join(f"{h['id']} | {h['kind']} | {h['who']} | due {h['due_weekday']} | "
                      f"{h['days_late']:+d} days" for h in history)
    current = {k: skill(k) for k in SKILL_TARGETS}
    r = router.ask("judge", _msgs(
        f"Below is {read_notes_owner()}'s record of closed promises (id | kind of work | person | weekday it "
        "was due | days late, negative = early). Find at most two patterns in WHERE they slip, specific enough "
        "to act on. Describe each pattern with one or more of these fields, using values exactly as they "
        f"appear in the record: kind ({', '.join(sorted({h['kind'] for h in history}))}), due_weekday, who. "
        "For each, write one plain rule Kept should follow from now on when it drafts replies that name a "
        "date (skill follow_up) or plans the day (skill brief). Code will count every promise that fits "
        "the pattern, so only propose a rule if most of them were late. A rule must make the date "
        "you GIVE match when the work really lands (later, or with a stated buffer), never an earlier day: "
        f"by the numbers, these kinds of work land late: {json.dumps(late_kinds)}. Do not repeat existing rules.\n"
        'Reply JSON: {"rules": [{"rule": "...", "skill": "follow_up|brief", "explain": "one sentence", '
        '"pattern": {"kind": "...", "due_weekday": "...", "who": "..."}}]}\n\n'
        f"Current skills:\n{json.dumps(current)}\n\nRecord:\n{table}"),
        purpose="weekly: learn rules from your history", json_mode=True, max_tokens=1200)
    try:
        rules = r.json().get("rules") or []
    except Exception as e:
        _abstain("learn", "weekly rules", Verdict(False, [f"model reply unusable: {e}"]))
        return []
    asked = []
    for rule in rules[:2]:
        v = shape(rule, {"rule": str, "skill": str, "pattern": dict})
        if v:
            if rule["skill"] not in SKILL_TARGETS:
                v.add(f"skill '{rule['skill']}' is not one of {SKILL_TARGETS}")
            v.merge(sendable_text(rule["rule"], max_chars=260))
            rows = matching(rule["pattern"], history)
            stats = evidence_stats(rows)
            if moves_earlier(rule["rule"], rule["pattern"]):
                v.add("the rule tells you to promise an earlier day, but these promises land late")
            if not any(k in rule["pattern"] and rule["pattern"][k] for k in PATTERN_KEYS):
                v.add("the pattern names no kind, weekday or person")
            if stats["n"] < MIN_EVIDENCE:
                v.add(f"only {stats['n']} promises behind this rule; need {MIN_EVIDENCE}")
            elif stats["share_late"] < MIN_LATE_SHARE:
                v.add(f"the evidence doesn't show a pattern: {stats['late']} of {stats['n']} were late")
        if not v:
            _abstain("learn", rule.get("rule", "rule")[:80] if isinstance(rule, dict) else "rule", v, rule)
            continue
        summary = (f"{stats['late']} of these {stats['n']} promises were late, typically by "
                   f"{stats['typical_days_late']} day{'s' if stats['typical_days_late'] != 1 else ''}")
        req = approvals.propose(
            "add_rule", {"skill": rule["skill"], "rule": rule["rule"].strip(), "evidence": summary},
            summary=f"New rule for '{rule['skill']}': {rule['rule'].strip()}",
            why=f"{str(rule.get('explain', '')).strip()} ({summary}; code counted every promise matching "
                f"{ {k: v for k, v in rule['pattern'].items() if k in PATTERN_KEYS and v} })",
            checks=[f"{stats['n']} closed promises behind it", f"{int(stats['share_late'] * 100)}% of them late",
                    "numbers recomputed by code"],
            reasoning=r.reasoning, model_label="Nemotron Ultra")
        asked.append(req)
    return asked


@approvals.action("add_rule", needs_approval=True)
def add_rule(args: dict) -> str:
    """Changing how Kept behaves is a decision, so it waits for a Yes like an email does."""
    p = Path(SKILLS) / f"{args['skill']}.md"
    text = p.read_text() if p.exists() else f"# Skill: {args['skill']}\n"
    if "## Learned from your history" not in text:
        text = text.rstrip() + "\n\n## Learned from your history\n"
    text = text.rstrip() + f"\n- {args['rule']} _(added {now_iso()[:10]}: {args['evidence']})_\n"
    p.write_text(text)
    journal(f"Learned a rule for {args['skill']}: {args['rule']}")
    return f"added to skills/{args['skill']}.md"
