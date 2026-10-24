import json
import os
import shutil
import tempfile
from pathlib import Path

import pytest

_TMP = tempfile.mkdtemp(prefix="kept-test-")
os.environ["KEPT_DATA_DIR"] = _TMP
os.environ["KEPT_DEMO"] = "1"
os.environ["KEPT_DAILY_BUDGET_USD"] = "5"
os.environ.pop("TELEGRAM_BOT_TOKEN", None)


class FakeBackend:
    """Answers by matching a keyword in the prompt. Records every call."""

    def __init__(self, rules):
        self.rules = rules
        self.calls = []

    def models(self):
        return ["nvidia/Nemotron-3-Nano-30B-A3B", "nvidia/Nemotron-3-Super-120B-A12B",
                "nvidia/Nemotron-3-Ultra-550b-a55b", "meta-llama/Llama-3.3-70B-Instruct"]

    def complete(self, model, messages, max_tokens, temperature, json_mode):
        prompt = messages[-1]["content"]
        self.calls.append((model, prompt))
        for key, reply in self.rules:
            if key in prompt:
                text = reply(prompt) if callable(reply) else reply
                return (text if isinstance(text, str) else json.dumps(text)), 100, 50
        return "{}", 10, 5


@pytest.fixture(autouse=True)
def clean_data():
    d = Path(_TMP)
    for p in d.iterdir():
        shutil.rmtree(p) if p.is_dir() else p.unlink()
    yield


@pytest.fixture
def fake(monkeypatch):
    from kept import llm

    def install(rules):
        fb = FakeBackend(rules)
        monkeypatch.setattr(llm.router, "backend", fb)
        llm.router._resolved.clear()
        return fb

    return install
