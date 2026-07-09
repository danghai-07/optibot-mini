"""Strip non-content HTML from Zendesk article bodies."""

from __future__ import annotations

from bs4 import BeautifulSoup, NavigableString, Tag

DROP_TAGS = frozenset(
    {
        "script",
        "style",
        "nav",
        "footer",
        "header",
        "iframe",
        "noscript",
        "svg",
        "form",
        "button",
    }
)


def clean_html(html: str) -> str:
    """Remove nav/chrome tags; keep headings, lists, code, tables, links."""
    if not html:
        return ""

    soup = BeautifulSoup(html, "lxml")

    for tag in soup.find_all(list(DROP_TAGS)):
        tag.decompose()

    # Zendesk often wraps related articles / feedback widgets
    for el in soup.select(
        ".related-articles, .article-votes, .article-sidebar, "
        ".sidenav, .breadcrumbs, .share, [data-test-id='article-vote']"
    ):
        el.decompose()

    # Drop empty paragraphs that only contain whitespace/br
    for p in soup.find_all("p"):
        if isinstance(p, Tag) and not p.get_text(strip=True) and not p.find("img"):
            p.decompose()

    body = soup.body if soup.body else soup
    return "".join(str(c) for c in body.children if not isinstance(c, NavigableString) or str(c).strip())
