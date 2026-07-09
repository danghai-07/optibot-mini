"""Fetch published articles from OptiSigns Zendesk Help Center API."""

from __future__ import annotations

import logging
import os
import re
from typing import Any

import requests

logger = logging.getLogger("optibot.scraper")

DEFAULT_BASE = "https://support.optisigns.com"
DEFAULT_LOCALE = "en-us"
USER_AGENT = "optibot-mini/1.0 (+take-home scraper)"


def _session() -> requests.Session:
    s = requests.Session()
    s.headers.update({"User-Agent": USER_AGENT, "Accept": "application/json"})
    return s


def slug_from_article(article: dict[str, Any]) -> str:
    """Derive a stable filesystem slug from html_url or title."""
    html_url = article.get("html_url") or ""
    m = re.search(r"/articles/\d+-([^/?#]+)", html_url)
    if m:
        return m.group(1).lower()

    title = (article.get("title") or f"article-{article.get('id')}").lower()
    slug = re.sub(r"[^a-z0-9]+", "-", title).strip("-")
    return slug or f"article-{article.get('id')}"


def fetch_all_articles(
    *,
    min_count: int = 30,
    base_url: str | None = None,
    locale: str | None = None,
    session: requests.Session | None = None,
) -> list[dict[str, Any]]:
    """Paginate Help Center articles until the catalog is exhausted.

    Returns article dicts enriched with ``slug``. Skips drafts and empty bodies.
    """
    base = (base_url or os.getenv("ZENDESK_BASE_URL", DEFAULT_BASE)).rstrip("/")
    loc = locale or os.getenv("ZENDESK_LOCALE", DEFAULT_LOCALE)
    sess = session or _session()

    url: str | None = f"{base}/api/v2/help_center/{loc}/articles.json"
    params: dict[str, Any] | None = {"per_page": 100}
    collected: list[dict[str, Any]] = []

    while url:
        logger.info("GET %s", url)
        resp = sess.get(url, params=params, timeout=60)
        resp.raise_for_status()
        payload = resp.json()

        for art in payload.get("articles") or []:
            if art.get("draft") is True:
                continue
            if not art.get("body"):
                continue
            enriched = dict(art)
            enriched["slug"] = slug_from_article(enriched)
            collected.append(enriched)

        url = payload.get("next_page")
        params = None  # next_page already includes query string

    if len(collected) < min_count:
        logger.warning("Only collected %d articles (min=%d)", len(collected), min_count)

    return collected
