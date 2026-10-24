"""Before and after: proof of the work, captured at the right moments.

For website work Kept doesn't need to remind anyone: when a project starts it takes a
screenshot of the client's current site, and when the launch promise is closed it takes
another. For any other kind of job it asks the owner for a photo at the start and at the
end, and the owner sends it from the dashboard. The finished-work post uses the pair.
"""
from __future__ import annotations

import re
import shutil
from pathlib import Path

import httpx

from .store import append_audit, data_dir, journal, locked, now_iso, read_json, write_json

FILE = "media.json"
SHOT = "https://image.thum.io/get/width/1200/crop/900/noanimate/{url}"


def slug(client: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", client.lower()).strip("-")


def folder(client: str) -> Path:
    d = data_dir() / "media" / slug(client)
    d.mkdir(parents=True, exist_ok=True)
    return d


def site_of(contract_text: str) -> str:
    m = re.search(r"\bsite:\s*(https?://\S+)", contract_text, re.I)
    return m.group(1).rstrip(".,") if m else ""


def record(client: str, which: str, path: Path, how: str) -> dict:
    with locked():
        rows = read_json(FILE, {})
        rows.setdefault(slug(client), {})[which] = {"path": str(path.relative_to(data_dir())), "how": how, "ts": now_iso()}
        write_json(FILE, rows)
    append_audit("media", client=client, which=which, how=how)
    journal(f"Saved the '{which}' picture for {client} ({how})")
    return rows[slug(client)]


def capture_site(client: str, which: str, url: str) -> dict | None:
    """Screenshot a live site. Returns the media record, or None if the site can't be captured."""
    if not url:
        return None
    try:
        r = httpx.get(SHOT.format(url=url), timeout=90, follow_redirects=True)
        if r.status_code != 200 or not r.headers.get("content-type", "").startswith("image/") or len(r.content) < 5000:
            raise RuntimeError(f"screenshot service returned {r.status_code}")
    except Exception as e:
        journal(f"Couldn't screenshot {url} for {client}: {e}")
        return None
    p = folder(client) / f"{which}.png"
    p.write_bytes(r.content)
    return record(client, which, p, f"screenshot of {url}")


def save_upload(client: str, which: str, filename: str, data: bytes) -> dict:
    ext = (Path(filename).suffix or ".jpg").lower()
    if ext not in (".jpg", ".jpeg", ".png", ".webp"):
        raise ValueError("photos only: jpg, png or webp")
    if len(data) > 8_000_000:
        raise ValueError("photo is larger than 8 MB")
    p = folder(client) / f"{which}{ext}"
    p.write_bytes(data)
    return record(client, which, p, "photo from the owner")


def pair(client: str) -> dict:
    return read_json(FILE, {}).get(slug(client), {})


def missing(client: str) -> list[str]:
    have = pair(client)
    return [w for w in ("before", "after") if w not in have]


def copy_demo(client: str, before: Path, after: Path) -> None:
    for which, src in (("before", before), ("after", after)):
        if src.exists():
            dst = folder(client) / f"{which}{src.suffix}"
            shutil.copy(src, dst)
            record(client, which, dst, "screenshot of the site")
