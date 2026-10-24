"""Ask Kept about your own week. Answers come only from Kept's files, and every
answer must point at the ledger rows or journal lines it used."""
from __future__ import annotations

import json

from . import ledger
from .llm import router
from .store import read_journal, read_notes
from .validators import Verdict, grounded


def ask(question: str) -> dict:
    rows = ledger.items()
    sources = {f"ledger:{r['id']}": json.dumps(r, ensure_ascii=False) for r in rows[-60:]}
    journal_text = read_journal(7)
    if journal_text:
        sources["journal"] = journal_text
    notes = read_notes()
    if notes:
        sources["notes"] = notes
    listing = "\n\n".join(f"[{k}]\n{v[:4000]}" for k, v in sources.items())
    r = router.ask("plan", [
        {"role": "system", "content": "You answer questions about the owner's own commitments using ONLY "
                                      "the records given. If the records don't say, answer that you don't know. Ledger rows have a "
                                      "status: keep what is still open apart from what is already done, and lead "
                                      "with what is open."},
        {"role": "user", "content": f"Question: {question}\n\nRecords:\n{listing}\n\n"
                                    'Reply JSON: {"answer": "...", "evidence": [{"source": "<id in brackets>", '
                                    '"quote": "exact words from that record"}]}'}],
        purpose="memory question", json_mode=True, max_tokens=600)
    try:
        d = r.json()
    except Exception as e:
        return {"answer": "I couldn't produce a usable answer.", "verified": False, "problems": [str(e)]}
    ev = d.get("evidence") or []
    v = grounded(ev, sources) if ev else Verdict(False, ["the answer cites no record"])
    return {"answer": d.get("answer", ""), "evidence": ev, "verified": v.ok, "problems": v.problems,
            "model": r.model}
