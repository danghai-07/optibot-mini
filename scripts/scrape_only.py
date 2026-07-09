"""Scrape-only helper: write Markdown articles without calling OpenAI.

Usage: python scripts/scrape_only.py
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from dotenv import load_dotenv

load_dotenv(ROOT / ".env")

from src.scraper.html_to_md import article_to_markdown, write_article_file
from src.scraper.zendesk_client import fetch_all_articles


def main() -> int:
    articles_dir = ROOT / os.getenv("ARTICLES_DIR", "data/articles")
    min_articles = int(os.getenv("MIN_ARTICLES", "30"))
    articles_dir.mkdir(parents=True, exist_ok=True)

    articles = fetch_all_articles(min_count=min_articles)
    print(f"Fetched {len(articles)} articles")
    if len(articles) < min_articles:
        print(f"ERROR: need >= {min_articles}", file=sys.stderr)
        return 1

    for art in articles:
        md = article_to_markdown(art)
        path = write_article_file(articles_dir, art, md)
        print(path.name)

    print(f"Wrote {len(articles)} files to {articles_dir}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
