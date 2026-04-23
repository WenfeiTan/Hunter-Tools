"""Google search acquisition via requests + BeautifulSoup."""

from __future__ import annotations

import hashlib
import json
import logging
import random
import time
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import quote_plus

import requests
from bs4 import BeautifulSoup
from requests import Response
from requests.adapters import HTTPAdapter
from requests.exceptions import ConnectionError as RequestsConnectionError
from requests.exceptions import RequestException, SSLError, Timeout
from urllib3.util.retry import Retry

from hunter_tools.config import DEFAULT_HEADERS
from hunter_tools.models import SearchResult
from hunter_tools.utils import normalize_text

GOOGLE_SEARCH_URL = "https://www.google.com/search"
logger = logging.getLogger(__name__)


class AntiBotDetectedError(RuntimeError):
    """Raised when Google anti-bot protection page is detected."""


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


class GoogleClient:
    def __init__(
        self,
        timeout_seconds: float = 15.0,
        max_retries: int = 3,
        backoff_seconds: float = 2.0,
        jitter_ratio: float = 0.35,
        blocked_cooldown_seconds: float = 25.0,
        raw_output_dir: str | None = "outputs/raw_pages",
    ):
        self.timeout_seconds = timeout_seconds
        self.max_retries = max_retries
        self.backoff_seconds = backoff_seconds
        self.jitter_ratio = jitter_ratio
        self.blocked_cooldown_seconds = blocked_cooldown_seconds
        self.raw_output_dir = Path(raw_output_dir) if raw_output_dir else None
        self.session = self._build_session()

    def search(self, query: str, pages: int = 2, page_size: int = 10, delay_seconds: float = 1.5) -> list[SearchResult]:
        logger.info("Stage[acquire] start query=%s pages=%s page_size=%s", query, pages, page_size)
        results: list[SearchResult] = []
        for page in range(pages):
            start = page * page_size
            url = f"{GOOGLE_SEARCH_URL}?q={quote_plus(query)}&num={page_size}&start={start}"
            logger.info("Stage[acquire] fetch query=%s page=%s start=%s", query, page + 1, start)
            response = self._fetch_with_retry(url)
            self._persist_raw_page(
                query=query,
                page=page + 1,
                start=start,
                html=response.text,
                request_url=url,
                final_url=response.url,
                mode="requests",
            )
            parsed = self._parse_google_html(response.text, query)
            results.extend(parsed)
            logger.info("Stage[acquire] parsed query=%s page=%s results=%s", query, page + 1, len(parsed))
            if page < pages - 1:
                sleep_seconds = self._with_jitter(delay_seconds)
                logger.debug("Stage[acquire] sleep_between_pages seconds=%.2f query=%s", sleep_seconds, query)
                time.sleep(sleep_seconds)
        logger.info("Stage[acquire] done query=%s total_results=%s", query, len(results))
        return results

    def _build_session(self) -> requests.Session:
        session = requests.Session()
        retry_policy = Retry(
            total=2,
            connect=2,
            read=2,
            backoff_factor=0.6,
            allowed_methods=["GET"],
            status_forcelist=[429, 500, 502, 503, 504],
            raise_on_status=False,
        )
        adapter = HTTPAdapter(max_retries=retry_policy)
        session.mount("https://", adapter)
        session.mount("http://", adapter)
        return session

    def _fetch_with_retry(self, url: str) -> Response:
        last_error: Exception | None = None
        for attempt in range(self.max_retries + 1):
            logger.debug("Stage[http] request attempt=%s/%s url=%s", attempt + 1, self.max_retries + 1, url)
            try:
                response = self.session.get(url, headers=DEFAULT_HEADERS, timeout=self.timeout_seconds)
            except (SSLError, Timeout, RequestsConnectionError) as exc:
                last_error = exc
                if attempt >= self.max_retries:
                    break
                sleep_seconds = self._retry_sleep(attempt)
                logger.warning("Stage[http] transient_error=%s retry_in=%.2fs", type(exc).__name__, sleep_seconds)
                time.sleep(sleep_seconds)
                continue

            if self._is_antibot_response(response):
                last_error = AntiBotDetectedError(f"Blocked by Google anti-bot page: {response.url}")
                if attempt >= self.max_retries:
                    break
                sleep_seconds = self._retry_sleep(attempt, blocked=True)
                logger.warning("Stage[http] antibot_detected retry_in=%.2fs url=%s", sleep_seconds, response.url)
                time.sleep(sleep_seconds)
                continue

            if response.status_code == 429:
                last_error = RequestException(f"Rate limited by Google (429): {response.url}")
                if attempt >= self.max_retries:
                    break
                sleep_seconds = self._retry_sleep(attempt, blocked=True)
                logger.warning("Stage[http] rate_limited_429 retry_in=%.2fs url=%s", sleep_seconds, response.url)
                time.sleep(sleep_seconds)
                continue

            try:
                response.raise_for_status()
            except RequestException as exc:
                last_error = exc
                if 500 <= response.status_code < 600 and attempt < self.max_retries:
                    sleep_seconds = self._retry_sleep(attempt)
                    logger.warning(
                        "Stage[http] server_error status=%s retry_in=%.2fs url=%s",
                        response.status_code,
                        sleep_seconds,
                        response.url,
                    )
                    time.sleep(sleep_seconds)
                    continue
                break

            return response

        if last_error:
            logger.error("Stage[http] exhausted_retries url=%s error=%s", url, last_error)
            raise last_error
        raise RuntimeError("Google fetch failed without explicit error")

    @staticmethod
    def _is_antibot_response(response: Response) -> bool:
        url_lower = response.url.lower()
        text_lower = response.text.lower()
        markers = (
            "/sorry/",
            "unusual traffic",
            "our systems have detected unusual traffic",
            "to continue, please type the characters below",
        )
        if response.status_code == 429:
            return True
        return any(marker in url_lower or marker in text_lower for marker in markers)

    def _retry_sleep(self, attempt: int, blocked: bool = False) -> float:
        base = self.blocked_cooldown_seconds if blocked else self.backoff_seconds
        return self._with_jitter(base * (2**attempt))

    def _with_jitter(self, seconds: float) -> float:
        spread = max(seconds * self.jitter_ratio, 0.0)
        return max(0.1, random.uniform(seconds - spread, seconds + spread))

    @staticmethod
    def _parse_google_html(html: str, query: str) -> list[SearchResult]:
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

    def _persist_raw_page(
        self,
        query: str,
        page: int,
        start: int,
        html: str,
        request_url: str,
        final_url: str,
        mode: str,
    ) -> None:
        persist_raw_page(
            output_dir=self.raw_output_dir,
            query=query,
            page=page,
            start=start,
            html=html,
            request_url=request_url,
            final_url=final_url,
            mode=mode,
        )
