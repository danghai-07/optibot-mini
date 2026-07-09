"""Convert cleaned Zendesk HTML articles into Markdown files."""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any
from urllib.parse import urljoin

from markdownify import markdownify as md

from src.scraper.cleaner import clean_html


def _yaml_escape(value: str) -> str:
    return value.replace("\\", "\\\\").replace('"', '\\"')


def _absolutize_relative_links(markdown: str, base_url: str) -> str:
    """Turn markdown relative links into absolute OptiSigns URLs when possible."""

    def repl(match: re.Match[str]) -> str:
        text, href = match.group(1), match.group(2)
        if href.startswith(("http://", "https://", "mailto:", "#")):
            return match.group(0)
        absolute = urljoin(base_url, href)
        return f"[{text}]({absolute})"

    return re.sub(r"\[([^\]]+)\]\(([^)]+)\)", repl, markdown)


def article_to_markdown(article: dict[str, Any]) -> str:
    title = (article.get("title") or "").strip()
    article_id = article.get("id")
    article_url = article.get("html_url") or ""
    updated_at = article.get("updated_at") or ""
    raw_html = article.get("body") or ""

    cleaned = clean_html(raw_html)
    body_md = md(cleaned, heading_style="ATX", bullets="-").strip()

    if article_url:
        body_md = _absolutize_relative_links(body_md, article_url)

    # Collapse excessive blank lines
    body_md = re.sub(r"\n{3,}", "\n\n", body_md).strip()

    frontmatter = (
        "---\n"
        f'title: "{_yaml_escape(title)}"\n'
        f"article_id: {article_id}\n"
        f"article_url: {article_url}\n"
        f"updated_at: {updated_at}\n"
        "---\n\n"
    )

    cite = f"Article URL: {article_url}\n\n" if article_url else ""
    heading = f"# {title}\n\n" if title else ""

    return frontmatter + cite + heading + body_md + "\n"


def write_article_file(articles_dir: Path, article: dict[str, Any], markdown: str) -> Path:
    slug = article.get("slug") or f"article-{article.get('id')}"
    # Sanitize path segment
    slug = re.sub(r"[^a-zA-Z0-9._-]+", "-", slug).strip("-").lower()
    path = articles_dir / f"{slug}.md"
    path.write_text(markdown, encoding="utf-8")
    return path
