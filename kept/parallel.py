"""Run independent model calls side by side.

A morning used to make ~40 calls one after another and took three to five minutes. Most of
them don't depend on each other (nine emails, three news topics, five money and growth jobs),
so they now run in a small thread pool. Order of results is kept; a budget stop still stops.
Writes to shared files are serialised by store.locked().
"""
from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from typing import Callable, Iterable, TypeVar

T = TypeVar("T")
R = TypeVar("R")

WORKERS = 6


def pmap(fn: Callable[[T], R], items: Iterable[T], workers: int = WORKERS) -> list[R]:
    items = list(items)
    if len(items) <= 1:
        return [fn(x) for x in items]
    with ThreadPoolExecutor(max_workers=min(workers, len(items))) as ex:
        futures = [ex.submit(fn, x) for x in items]
        return [f.result() for f in futures]  # re-raises the first error (e.g. BudgetExceeded)
