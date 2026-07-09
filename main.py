"""Daily scrape → delta detect → Gemini File Search store sync.

Usage:
  python main.py
  docker run --rm -e GEMINI_API_KEY=... -e GEMINI_FILE_SEARCH_STORE=... <image>
"""

from __future__ import annotations

import json
import logging
import os
import sys
from pathlib import Path

from dotenv import load_dotenv

# Ensure repo root is on path when run as script
ROOT = Path(__file__).resolve().parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

load_dotenv(ROOT / ".env")

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(message)s",
    datefmt="%Y-%m-%dT%H:%M:%S",
)
logger = logging.getLogger("optibot")


def main() -> int:
    from src.scraper.zendesk_client import fetch_all_articles
    from src.scraper.html_to_md import article_to_markdown, write_article_file
    from src.state.manifest import (
        content_hash,
        load_manifest,
        save_manifest,
        upsert_entry,
    )
    from src.uploader.gemini_sync import GeminiSync

    articles_dir = Path(os.getenv("ARTICLES_DIR", "data/articles"))
    manifest_path = Path(os.getenv("MANIFEST_PATH", "state/manifest.json"))
    min_articles = int(os.getenv("MIN_ARTICLES", "30"))
    max_articles_raw = os.getenv("MAX_ARTICLES", "").strip()
    max_articles = int(max_articles_raw) if max_articles_raw else None

    api_key = os.getenv("GEMINI_API_KEY")
    file_search_store = os.getenv("GEMINI_FILE_SEARCH_STORE")
    if not api_key:
        logger.error("GEMINI_API_KEY is required")
        return 1
    if not file_search_store:
        logger.error("GEMINI_FILE_SEARCH_STORE is required")
        return 1

    articles_dir.mkdir(parents=True, exist_ok=True)
    manifest_path.parent.mkdir(parents=True, exist_ok=True)

    logger.info("Fetching articles from Zendesk Help Center…")
    articles = fetch_all_articles(min_count=min_articles)
    logger.info("Fetched %d articles", len(articles))

    if len(articles) < min_articles:
        logger.error("Expected >= %d articles, got %d", min_articles, len(articles))
        return 1

    if max_articles is not None and max_articles > 0:
        articles = articles[:max_articles]
        logger.info("MAX_ARTICLES=%d → processing %d articles", max_articles, len(articles))

    manifest = load_manifest(manifest_path)
    sync = GeminiSync(api_key=api_key, file_search_store=file_search_store)

    stats = {"added": 0, "updated": 0, "skipped": 0, "files_uploaded": 0, "chunks_embedded": 0}

    for article in articles:
        md_text = article_to_markdown(article)
        md_path = write_article_file(articles_dir, article, md_text)
        digest = content_hash(md_text)
        article_id = str(article["id"])
        prev = manifest.get("articles", {}).get(article_id)

        if prev and prev.get("hash") == digest and prev.get("document_id"):
            stats["skipped"] += 1
            logger.info("skip id=%s slug=%s", article_id, article.get("slug"))
            continue

        is_update = prev is not None and bool(prev.get("document_id"))
        if is_update and prev.get("document_id"):
            sync.remove_document(prev["document_id"])

        document_id, chunk_count = sync.upload_markdown(md_path)
        stats["files_uploaded"] += 1
        stats["chunks_embedded"] += chunk_count

        upsert_entry(
            manifest,
            article_id=article_id,
            entry={
                "hash": digest,
                "slug": article.get("slug") or md_path.stem,
                "article_url": article.get("html_url", ""),
                "updated_at": article.get("updated_at", ""),
                "document_id": document_id,
                "path": str(md_path.as_posix()),
            },
        )

        if is_update:
            stats["updated"] += 1
            logger.info("updated id=%s doc=%s chunks≈%s", article_id, document_id, chunk_count)
        else:
            stats["added"] += 1
            logger.info("added id=%s doc=%s chunks≈%s", article_id, document_id, chunk_count)

    save_manifest(manifest_path, manifest)

    summary = {
        "added": stats["added"],
        "updated": stats["updated"],
        "skipped": stats["skipped"],
        "files_uploaded": stats["files_uploaded"],
        "chunks_embedded": stats["chunks_embedded"],
        "total_articles": len(articles),
    }
    print(json.dumps(summary))
    logger.info("Done: %s", summary)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
