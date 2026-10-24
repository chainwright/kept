"""Talking to NVIDIA Nemotron on Nebius Token Factory, with routing you can see.

Every call names its tier and the reason, and is written to the audit log with
tokens, latency and cost. A daily budget stops runaway spend before it happens.
"""
from __future__ import annotations

import json
import re
import time
from dataclasses import dataclass
from typing import Any, Protocol

from .config import TIERS, settings
from .store import append_audit, now, read_audit

# what kind of work goes to which size of model, and why
ROUTES = {
    "classify": "nano",     # is this email a lead, a bill, or noise?
    "extract": "nano",      # pull the promise and the date out of a message
    "plan": "super",        # what should today look like
    "draft": "super",       # write the follow-up a human will read
    "judge": "ultra",       # the one call where being wrong costs money or trust
}


class BudgetExceeded(RuntimeError):
    pass


@dataclass
class Reply:
    text: str
    model: str
    tier: str
    prompt_tokens: int
    completion_tokens: int
    usd: float
    ms: int

    def json(self) -> Any:
        return parse_json(self.text)


class Backend(Protocol):
    def complete(self, model: str, messages: list[dict], max_tokens: int,
                 temperature: float, json_mode: bool) -> tuple[str, int, int]: ...


def parse_json(text: str) -> Any:
    """Models wrap JSON in prose or code fences more often than they admit."""
    text = re.sub(r"<think>.*?</think>", "", text, flags=re.S).strip()
    m = re.search(r"```(?:json)?\s*(.*?)```", text, flags=re.S)
    if m:
        text = m.group(1)
    start = min([i for i in (text.find("{"), text.find("[")) if i >= 0], default=-1)
    if start < 0:
        raise ValueError("no JSON object in model reply")
    return json.JSONDecoder().raw_decode(text[start:])[0]


class NebiusBackend:
    def __init__(self) -> None:
        from openai import OpenAI

        self.client = OpenAI(base_url=settings.nebius_base_url, api_key=settings.nebius_api_key)
        self._models: list[str] | None = None

    def models(self) -> list[str]:
        if self._models is None:
            try:
                self._models = [m.id for m in self.client.models.list().data]
            except Exception:
                self._models = []
        return self._models

    def complete(self, model, messages, max_tokens, temperature, json_mode):
        kw: dict[str, Any] = {}
        if json_mode:
            kw["response_format"] = {"type": "json_object"}
        r = self.client.chat.completions.create(
            model=model, messages=messages, max_tokens=max_tokens,
            temperature=temperature, **kw)
        u = r.usage
        return (r.choices[0].message.content or "",
                getattr(u, "prompt_tokens", 0) or 0,
                getattr(u, "completion_tokens", 0) or 0)


class Router:
    def __init__(self, backend: Backend | None = None) -> None:
        self.backend = backend
        self._resolved: dict[str, str] = {}

    def _backend(self) -> Backend:
        if self.backend is None:
            self.backend = NebiusBackend()
        return self.backend

    def model_for(self, tier: str) -> str:
        if tier in self._resolved:
            return self._resolved[tier]
        t = TIERS[tier]
        model = settings.model_override(tier)
        if not model:
            listed = getattr(self._backend(), "models", lambda: [])()
            hits = [m for m in listed if "nemotron" in m.lower() and t.model_hint in m.lower()]
            # prefer the plain instruct model over vision / fine-tune variants
            hits.sort(key=lambda m: (("vl" in m.lower()) or ("lora" in m.lower()), len(m)))
            model = hits[0] if hits else t.default_model
        self._resolved[tier] = model
        return model

    @staticmethod
    def spent_today() -> float:
        today = now().date().isoformat()
        return sum(r.get("usd", 0.0) for r in read_audit(5000)
                   if r.get("kind") == "llm" and r.get("ts", "").startswith(today))

    def ask(self, task: str, messages: list[dict], *, purpose: str, max_tokens: int = 800,
            temperature: float = 0.2, json_mode: bool = False, tier: str | None = None) -> Reply:
        tier = tier or ROUTES[task]
        t = TIERS[tier]
        if self.spent_today() >= settings.daily_budget_usd:
            append_audit("llm_refused", task=task, tier=tier, purpose=purpose,
                         reason=f"daily budget ${settings.daily_budget_usd:.2f} reached")
            raise BudgetExceeded(f"daily model budget ${settings.daily_budget_usd:.2f} reached")
        model = self.model_for(tier)
        t0 = time.time()
        text, pin, pout = self._backend().complete(model, messages, max_tokens, temperature, json_mode)
        ms = int((time.time() - t0) * 1000)
        usd = pin / 1e6 * t.usd_in_per_m + pout / 1e6 * t.usd_out_per_m
        append_audit("llm", task=task, tier=tier, model=model, why=t.why, purpose=purpose,
                     prompt_tokens=pin, completion_tokens=pout, usd=round(usd, 6), ms=ms)
        return Reply(text, model, tier, pin, pout, usd, ms)


router = Router()
