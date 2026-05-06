"""Shared Google SERP page utilities (parse, anti-bot detect, raw persistence)."""

from __future__ import annotations

import hashlib
import json
import logging
from datetime import datetime, timezone
from pathlib import Path

from bs4 import BeautifulSoup

from hunter_tools.models import SearchResult
from hunter_tools.utils import normalize_text

logger = logging.getLogger(__name__)


class AntiBotDetectedError(RuntimeError):
    """Raised when Google anti-bot protection page is detected."""


def is_antibot_page(url: str, html: str, status_code: int | None = None) -> bool:
    url_lower = (url or "").lower()
    text_lower = (html or "").lower()
    markers = (
        "unusual traffic",
        "our systems have detected unusual traffic",
        "to continue, please type the characters below",
        "recaptcha",
        "i'm not a robot",
        "verify you are human",
        "please verify you are not a robot",
    )
    if status_code == 429:
        logger.warning("Stage[antibot] detected via status_code=429")
        return True
    for marker in markers:
        if marker in url_lower or marker in text_lower:
            logger.warning("Stage[antibot] detected marker='%s' in url or html", marker)
            return True
    return False


def parse_google_html(html: str, query: str) -> list[SearchResult]:
    soup = BeautifulSoup(html, "html.parser")
    parsed: list[SearchResult] = []

    for block in soup.select("div.g, div.MjjYud"):
        h3 = block.select_one("h3")
        if h3:
            link_tag = h3.find_parent("a", href=True) or block.select_one("a[href]")
        else:
            link_tag = block.select_one("a[href]")

        snippet_node = block.select_one(
            "div.VwiC3b, span.aCOpRe, div.IsZvec, div[data-sncf], div[data-content-feature]"
        )
        if not h3 or not link_tag:
            continue

        title = normalize_text(h3.get_text(" ", strip=True))
        link = normalize_text(link_tag.get("href", ""))
        snippet = normalize_text(snippet_node.get_text(" ", strip=True) if snippet_node else "")

        if not title or not link:
            continue

        parsed.append(SearchResult(title=title, link=link, snippet=snippet, query=query))

    return parsed


def persist_raw_page(
    output_dir: Path | None,
    query: str,
    page: int,
    start: int,
    html: str,
    request_url: str,
    final_url: str,
    mode: str,
) -> None:
    if output_dir is None:
        return

    output_dir.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    query_digest = hashlib.sha1(query.encode("utf-8")).hexdigest()[:10]
    stem = f"{timestamp}_q{query_digest}_p{page}_s{start}_{mode}"

    html_path = output_dir / f"{stem}.html"
    meta_path = output_dir / f"{stem}.json"

    html_path.write_text(html, encoding="utf-8")
    meta = {
        "query": query,
        "page": page,
        "start": start,
        "request_url": request_url,
        "final_url": final_url,
        "saved_at_utc": timestamp,
        "mode": mode,
    }
    meta_path.write_text(json.dumps(meta, ensure_ascii=False, indent=2), encoding="utf-8")
    logger.info("Stage[raw] saved html=%s meta=%s", html_path, meta_path)

