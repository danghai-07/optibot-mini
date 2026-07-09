"""Persistent manifest for delta detection (SHA-256 of Markdown)."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any


def content_hash(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def load_manifest(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {"version": 1, "articles": {}}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return {"version": 1, "articles": {}}
    if "articles" not in data or not isinstance(data["articles"], dict):
        data = {"version": 1, "articles": {}}
    return data


def save_manifest(path: Path, manifest: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(manifest, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )


def upsert_entry(manifest: dict[str, Any], *, article_id: str, entry: dict[str, Any]) -> None:
    articles = manifest.setdefault("articles", {})
    articles[article_id] = entry
