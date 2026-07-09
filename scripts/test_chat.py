"""Sanity-check OptiBot against the Gemini File Search store (API test).

Usage:
  python scripts/test_chat.py
  python scripts/test_chat.py "How do I add a YouTube video?"
"""

from __future__ import annotations

import os
import re
import sys
from pathlib import Path

from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parents[1]
load_dotenv(ROOT / ".env")

if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.prompts import OPTIBOT_CITATION_ADDENDUM, OPTIBOT_SYSTEM_PROMPT

DEFAULT_QUESTION = "How do I add a YouTube video?"
MAX_CITATIONS = 3

SUPPORT_ARTICLE_URL = re.compile(
    r"https://support\.optisigns\.com/hc/en-us/articles/\d+[^\s\)\]>\"']*",
    re.IGNORECASE,
)
ARTICLE_URL_LINE = re.compile(
    r"^Article URL:\s*(.+)$",
    re.MULTILINE | re.IGNORECASE,
)
FRONTMATTER_ARTICLE_URL = re.compile(
    r"^article_url:\s*(https://support\.optisigns\.com/[^\s]+)\s*$",
    re.MULTILINE | re.IGNORECASE,
)
CANONICAL_ARTICLE_URL_LINE = re.compile(
    r"^Article URL:\s*(https://support\.optisigns\.com/[^\s]+)\s*$",
    re.MULTILINE | re.IGNORECASE,
)


def _canonical_url_from_chunk_text(text: str) -> str | None:
    """Prefer frontmatter article_url, then body 'Article URL:' line — not inline links."""
    for pattern in (FRONTMATTER_ARTICLE_URL, CANONICAL_ARTICLE_URL_LINE):
        match = pattern.search(text)
        if match:
            return match.group(1).rstrip(".,;)")
    return None

def _url_from_local_article(title: str) -> str | None:
    """Read canonical article_url from scraped Markdown when chunks omit frontmatter."""
    name = title if title.endswith(".md") else f"{title}.md"
    path = ROOT / "data" / "articles" / name
    if not path.is_file():
        return None
    try:
        head = path.read_text(encoding="utf-8", errors="replace")[:8000]
    except OSError:
        return None
    return _canonical_url_from_chunk_text(head)


def _grounding_chunks(response):
    candidates = getattr(response, "candidates", None) or []
    if not candidates:
        return []
    metadata = getattr(candidates[0], "grounding_metadata", None)
    if not metadata:
        return []
    return getattr(metadata, "grounding_chunks", None) or []


def _grounding_doc_pairs(response) -> list[tuple[str, str]]:
    """(document_title, canonical_url) in retrieval order, one entry per document."""
    chunks = _grounding_chunks(response)
    doc_urls: dict[str, str] = {}

    for chunk in chunks:
        ctx = getattr(chunk, "retrieved_context", None)
        if not ctx:
            continue
        title = (getattr(ctx, "title", None) or getattr(ctx, "uri", None) or "").strip()
        text = getattr(ctx, "text", None) or ""
        url = _canonical_url_from_chunk_text(text)
        if title and url:
            doc_urls[title] = url
        elif title and title not in doc_urls:
            local = _url_from_local_article(title)
            if local:
                doc_urls[title] = local

    seen_titles: set[str] = set()
    pairs: list[tuple[str, str]] = []
    for chunk in chunks:
        ctx = getattr(chunk, "retrieved_context", None)
        if not ctx:
            continue
        title = (getattr(ctx, "title", None) or getattr(ctx, "uri", None) or "").strip()
        if not title or title in seen_titles:
            continue
        seen_titles.add(title)

        chunk_url = doc_urls.get(title)
        if not chunk_url:
            text = getattr(ctx, "text", None) or ""
            chunk_url = _canonical_url_from_chunk_text(text)
        if not chunk_url:
            chunk_url = _url_from_local_article(title)
        if not chunk_url:
            continue
        pairs.append((title, chunk_url))
    return pairs


def _rank_grounding_urls(
    pairs: list[tuple[str, str]],
    *,
    question: str,
    body: str,
) -> list[str]:
    """Rank retrieved docs by overlap with the question and answer text."""
    if not pairs:
        return []

    question_tokens = {
        t for t in re.findall(r"[a-z0-9]+", question.lower()) if len(t) > 2
    }
    body_lower = body.lower()

    def score(pair: tuple[str, str]) -> int:
        title, url = pair
        slug = title.removesuffix(".md").replace("-", " ").lower()
        slug_tokens = {t for t in slug.split() if len(t) > 2}
        value = 0
        for token in question_tokens:
            if token in slug or token in url.lower():
                value += 3
        for token in slug_tokens:
            if token in body_lower:
                value += 2
        if "youtube" in slug and ("youtube" in body_lower or "youtube" in question.lower()):
            value += 5
        if "website" in slug and "website" in body_lower:
            value += 4
        return value

    ranked = sorted(pairs, key=score, reverse=True)
    seen: set[str] = set()
    urls: list[str] = []
    for _, url in ranked:
        if url in seen:
            continue
        seen.add(url)
        urls.append(url)
    return urls


def _urls_from_grounding(response) -> list[str]:
    return [url for _, url in _grounding_doc_pairs(response)]


def _is_valid_citation(value: str) -> bool:
    value = value.strip()
    return bool(SUPPORT_ARTICLE_URL.fullmatch(value.rstrip(".,;)")))


def normalize_reply(
    text: str,
    grounding_pairs: list[tuple[str, str]],
    *,
    question: str,
) -> str:
    """Drop bad/hallucinated citations; fill from ranked grounding docs."""
    body = text or ""
    allowed = {url for _, url in grounding_pairs}
    ranked = _rank_grounding_urls(grounding_pairs, question=question, body=body)

    kept: list[str] = []
    had_bad = False
    for match in ARTICLE_URL_LINE.finditer(body):
        cite = match.group(1).strip().rstrip(".,;)")
        if _is_valid_citation(cite) and cite in allowed:
            kept.append(cite)
        else:
            had_bad = True

    if had_bad or not kept:
        kept = ranked[:MAX_CITATIONS]
    else:
        kept = kept[:MAX_CITATIONS]

    body = ARTICLE_URL_LINE.sub("", body).rstrip()
    if kept:
        citation_block = "\n".join(f"Article URL: {url}" for url in kept)
        return f"{body}\n\n{citation_block}".strip()
    return body.strip()


def _print_grounding(response) -> None:
    chunks = _grounding_chunks(response)
    if not chunks:
        return
    print("\n--- Sources (grounding) ---")
    for i, chunk in enumerate(chunks, 1):
        ctx = getattr(chunk, "retrieved_context", None)
        if not ctx:
            continue
        title = getattr(ctx, "title", None) or getattr(ctx, "uri", None) or "?"
        text = (getattr(ctx, "text", None) or "")[:200]
        print(f"{i}. {title}")
        if text:
            print(f"   {text}...")


def main() -> int:
    from google import genai

    api_key = os.getenv("GEMINI_API_KEY")
    store = os.getenv("GEMINI_FILE_SEARCH_STORE")
    if not api_key:
        print("Set GEMINI_API_KEY in .env", file=sys.stderr)
        return 1
    if not store:
        print("Set GEMINI_FILE_SEARCH_STORE in .env", file=sys.stderr)
        return 1

    question = " ".join(sys.argv[1:]).strip() or os.getenv("TEST_QUESTION", DEFAULT_QUESTION)
    model = os.getenv("GEMINI_CHAT_MODEL", "gemini-2.5-flash")
    system_instruction = f"{OPTIBOT_SYSTEM_PROMPT.strip()}\n{OPTIBOT_CITATION_ADDENDUM.strip()}"

    client = genai.Client(api_key=api_key)
    print(f"Model: {model}")
    print(f"Store: {store}")
    print(f"Question: {question}\n")

    response = client.models.generate_content(
        model=model,
        contents=question,
        config={
            "system_instruction": system_instruction,
            "tools": [{"file_search": {"file_search_store_names": [store]}}],
        },
    )

    raw = response.text or ""
    grounding_pairs = _grounding_doc_pairs(response)
    reply = normalize_reply(raw, grounding_pairs, question=question)

    print("--- OptiBot ---")
    print(reply or "(empty response)")
    if raw.strip() != reply.strip():
        print("\n--- (raw model output had citations normalized) ---")
    _print_grounding(response)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
