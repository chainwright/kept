"""Live web search through Tavily. Results become *sources* the validators can check
claims against, so search here is for grounding, not decoration."""
from __future__ import annotations

import hashlib

import httpx

from ..config import settings
from ..store import append_audit


def source_id(url: str) -> str:
    return "web:" + hashlib.sha1(url.encode()).hexdigest()[:8]


def search(query: str, *, max_results: int = 5, days: int | None = 7, topic: str = "news",
           depth: str = "advanced") -> list[dict]:
    """Returns [{id, title, url, content, published}] with full-ish page text in content."""
    if not settings.tavily_api_key:
        raise RuntimeError("TAVILY_API_KEY is not set")
    body = {"query": query, "max_results": max_results, "topic": topic,
            "include_raw_content": True, "search_depth": depth}
    if days:
        body["days"] = days
    r = httpx.post("https://api.tavily.com/search", json=body, timeout=40,
                   headers={"Authorization": f"Bearer {settings.tavily_api_key}"})
    r.raise_for_status()
    out = []
    for it in r.json().get("results", []):
        text = (it.get("raw_content") or it.get("content") or "")[:12000]
        out.append({"id": source_id(it["url"]), "title": it.get("title", ""), "url": it["url"],
                    "content": text, "published": it.get("published_date", "")})
    append_audit("search", query=query, results=len(out))
    return out


def extract(urls: list[str]) -> list[dict]:
    """Read pages Kept already knows the address of (a client's current site). Same shape as search."""
    if not settings.tavily_api_key:
        raise RuntimeError("TAVILY_API_KEY is not set")
    r = httpx.post("https://api.tavily.com/extract", json={"urls": urls[:5], "extract_depth": "basic"}, timeout=40,
                   headers={"Authorization": f"Bearer {settings.tavily_api_key}"})
    r.raise_for_status()
    out = [{"id": source_id(it["url"]), "title": it["url"], "url": it["url"],
            "content": (it.get("raw_content") or "")[:12000], "published": ""}
           for it in r.json().get("results", []) if it.get("raw_content")]
    append_audit("search_extract", urls=urls[:5], results=len(out))
    return out
