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
    "extract": "super",     # pull promises out of a thread: Nano without reasoning mixed up who owes whom
    "spot": "nano",         # find promises in a short draft the owner is about to send
    "plan": "super",        # what should today look like
    "draft": "super",       # write the follow-up a human will read
    "judge": "ultra",       # the one call where being wrong costs money or trust
    "see": "vision",        # read a client's photo of their kitchen
}


THINK_ALLOWANCE = 3000  # extra tokens for Super/Ultra to reason before the answer


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
    reasoning: str = ""
    finish: str = "stop"

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
    try:
        return json.JSONDecoder().raw_decode(text[start:])[0]
    except json.JSONDecodeError:
        # some replies come back as a Python-style dict ({'a': True}); parse that safely, never eval
        import ast
        end = max(text.rfind("}"), text.rfind("]")) + 1
        val = ast.literal_eval(text[start:end])
        if not isinstance(val, (dict, list)):
            raise
        return val


class NebiusBackend:
    def __init__(self) -> None:
        import httpx
        from openai import OpenAI

        # eval run 1: two jobs died on "Request timed out" — the SDK's 5 s connect timeout is too
        # tight for a home Wi-Fi line; reasoning calls can also take minutes, so allow both
        self.client = OpenAI(base_url=settings.nebius_base_url, api_key=settings.nebius_api_key,
                             timeout=httpx.Timeout(240, connect=30), max_retries=3)
        self._models: list[str] | None = None

    def models(self) -> list[str]:
        if self._models is None:
            try:
                self._models = [m.id for m in self.client.models.list().data]
            except Exception:
                self._models = []
        return self._models

    def complete(self, model, messages, max_tokens, temperature, json_mode, thinking=True):
        import time as _time

        from openai import APIStatusError, APITimeoutError, InternalServerError

        kw: dict[str, Any] = {}
        if json_mode:
            kw["response_format"] = {"type": "json_object"}
        if not thinking:
            # Nemotron 3 reasons by default. For sorting and extraction that hidden reasoning
            # ate the whole token budget and left an empty answer, so Nano runs with it off.
            kw["extra_body"] = {"chat_template_kwargs": {"enable_thinking": False}}
        # Token Factory had an intermittent 503 window on Oct 24 that outlasted the SDK's own
        # fast retries. We wait longer here so one flaky minute doesn't fail a whole morning.
        last: Exception | None = None
        for attempt in range(6):
            try:
                r = self.client.chat.completions.create(
                    model=model, messages=messages, max_tokens=max_tokens,
                    temperature=temperature, **kw)
                break
            except (InternalServerError, APITimeoutError) as e:
                last = e
            except APIStatusError as e:
                if e.status_code not in (500, 502, 503, 504, 429):
                    raise
                last = e
            _time.sleep(min(30, 5 * (attempt + 1)))
        else:
            raise last  # type: ignore[misc]
        u, ch = r.usage, r.choices[0]
        return (ch.message.content or "",
                getattr(u, "prompt_tokens", 0) or 0,
                getattr(u, "completion_tokens", 0) or 0,
                getattr(ch.message, "reasoning_content", None) or "",
                ch.finish_reason or "stop")


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
            # prefer the plain instruct model over vision / fine-tune variants (except for the vision tier)
            want_vl = "vl" in t.model_hint
            hits.sort(key=lambda m: ((("vl" in m.lower()) != want_vl) or ("lora" in m.lower()), len(m)))
            model = hits[0] if hits else t.default_model
        self._resolved[tier] = model
        return model

    @staticmethod
    def spent_today() -> float:
        today = now().date().isoformat()
        return sum(r.get("usd", 0.0) for r in read_audit(5000)
                   if r.get("kind") == "llm" and r.get("ts", "").startswith(today))

    def ask(self, task: str, messages: list[dict], *, purpose: str, max_tokens: int = 800,
            temperature: float = 0.2, json_mode: bool = False, tier: str | None = None,
            _retry: bool = False) -> Reply:
        tier = tier or ROUTES[task]
        t = TIERS[tier]
        if self.spent_today() >= settings.daily_budget_usd:
            append_audit("llm_refused", task=task, tier=tier, purpose=purpose,
                         reason=f"daily budget ${settings.daily_budget_usd:.2f} reached")
            raise BudgetExceeded(f"daily model budget ${settings.daily_budget_usd:.2f} reached")
        model = self.model_for(tier)
        # thinking tiers need room to reason *and* answer
        budget = max_tokens + (THINK_ALLOWANCE if t.thinking else 0)
        t0 = time.time()
        out = self._backend().complete(model, messages, budget, temperature, json_mode, t.thinking)
        text, pin, pout = out[:3]
        reasoning, finish = (out[3], out[4]) if len(out) >= 5 else ("", "stop")
        ms = int((time.time() - t0) * 1000)
        usd = pin / 1e6 * t.usd_in_per_m + pout / 1e6 * t.usd_out_per_m
        append_audit("llm", task=task, tier=tier, model=model, why=t.why, purpose=purpose,
                     thinking=t.thinking, prompt_tokens=pin, completion_tokens=pout,
                     usd=round(usd, 6), ms=ms, finish=finish,
                     reasoning=reasoning[:1500] if task == "judge" else None)
        cut_off = finish == "length"
        bad_json = False
        if json_mode:
            try:
                parse_json(text)
            except Exception:
                bad_json = True
        if (cut_off and (json_mode or not text.strip())) or bad_json:
            if not _retry:
                # The recorded demo run showed what "broken JSON" from Ultra really was: its reasoning
                # used the whole budget (3,900 of 3,900 tokens) and the answer was cut off. Retrying
                # with the same budget failed the same way, so the retry gets twice the room to think.
                append_audit("llm_retry", task=task, tier=tier, purpose=purpose,
                             error="ran out of tokens" if cut_off else "unusable JSON")
                return self.ask(task, messages, purpose=purpose, max_tokens=max_tokens * 2 if not t.thinking
                                else max_tokens + THINK_ALLOWANCE, temperature=temperature,
                                json_mode=json_mode, tier=tier, _retry=True)
            if cut_off and not text.strip():
                raise ValueError(f"{tier} ran out of tokens before answering ({pout} used)")
        return Reply(text, model, tier, pin, pout, usd, ms, reasoning, finish)


router = Router()
