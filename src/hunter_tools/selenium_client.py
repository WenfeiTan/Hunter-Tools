"""Google search acquisition via Selenium browser automation."""

from __future__ import annotations

import logging
import random
import time
from urllib.parse import quote_plus

from selenium import webdriver
from selenium.common.exceptions import TimeoutException, WebDriverException
from selenium.webdriver.chrome.options import Options

from pathlib import Path

from hunter_tools.google_page import (
    AntiBotDetectedError,
    is_antibot_page,
    parse_google_html,
    persist_raw_page,
)
from hunter_tools.models import SearchResult

logger = logging.getLogger(__name__)
GOOGLE_SEARCH_URL = "https://www.google.com/search"


class SeleniumGoogleClient:
    def __init__(
        self,
        timeout_seconds: float = 25.0,
        jitter_ratio: float = 0.35,
        blocked_cooldown_seconds: float = 25.0,
        headless: bool = True,
        raw_output_dir: str | None = "outputs/raw_pages",
        manual_antibot: bool = False,
        manual_antibot_timeout_seconds: float = 180.0,
        manual_antibot_poll_seconds: float = 2.0,
    ):
        self.timeout_seconds = timeout_seconds
        self.jitter_ratio = jitter_ratio
        self.blocked_cooldown_seconds = blocked_cooldown_seconds
        self.headless = headless
        self.raw_output_dir = Path(raw_output_dir) if raw_output_dir else None
        self.manual_antibot = manual_antibot
        self.manual_antibot_timeout_seconds = manual_antibot_timeout_seconds
        self.manual_antibot_poll_seconds = manual_antibot_poll_seconds
        self.driver = self._build_driver()

    def _build_driver(self) -> webdriver.Chrome:
        options = Options()
        if self.headless:
            options.add_argument("--headless=new")
        options.add_argument("--disable-blink-features=AutomationControlled")
        options.add_argument("--window-size=1400,1200")
        options.add_argument("--lang=en-US")
        options.add_argument(
            "--user-agent=Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/124.0.0.0 Safari/537.36"
        )
        driver = webdriver.Chrome(options=options)
        driver.set_page_load_timeout(self.timeout_seconds)
        return driver

    def close(self) -> None:
        try:
            self.driver.quit()
        except WebDriverException:
            logger.debug("Stage[acquire] selenium driver quit skipped due to WebDriverException")

    def search(self, query: str, pages: int = 2, page_size: int = 10, delay_seconds: float = 1.5) -> list[SearchResult]:
        logger.info("Stage[acquire] start query=%s pages=%s page_size=%s mode=selenium", query, pages, page_size)
        results: list[SearchResult] = []
        for page in range(pages):
            start = page * page_size
            url = f"{GOOGLE_SEARCH_URL}?q={quote_plus(query)}&num={page_size}&start={start}"
            logger.info("Stage[acquire] fetch query=%s page=%s start=%s mode=selenium", query, page + 1, start)
            try:
                html = self._fetch_page_source(url)
            except Exception:  # pylint: disable=broad-except
                if results:
                    logger.warning(
                        "Stage[acquire] page_failed_partial_return query=%s page=%s collected_results=%s",
                        query,
                        page + 1,
                        len(results),
                    )
                    return results
                raise
            persist_raw_page(
                output_dir=self.raw_output_dir,
                query=query,
                page=page + 1,
                start=start,
                html=html,
                request_url=url,
                final_url=self.driver.current_url or url,
                mode="selenium",
            )
            parsed = parse_google_html(html, query)
            results.extend(parsed)
            logger.info("Stage[acquire] parsed query=%s page=%s results=%s mode=selenium", query, page + 1, len(parsed))
            if not parsed:
                logger.warning(
                    "Stage[acquire] parsed_empty query=%s page=%s start=%s mode=selenium",
                    query,
                    page + 1,
                    start,
                )
            if page < pages - 1:
                sleep_seconds = self._with_jitter(delay_seconds)
                logger.debug("Stage[acquire] sleep_between_pages seconds=%.2f query=%s", sleep_seconds, query)
                time.sleep(sleep_seconds)
        logger.info("Stage[acquire] done query=%s total_results=%s mode=selenium", query, len(results))
        return results

    def _fetch_page_source(self, url: str) -> str:
        try:
            self.driver.get(url)
        except TimeoutException as exc:
            raise RuntimeError(f"Selenium page load timeout: {url}") from exc
        except WebDriverException as exc:
            raise RuntimeError(f"Selenium page load failed: {url}") from exc

        current_url = (self.driver.current_url or "").lower()
        html = self.driver.page_source or ""
        if is_antibot_page(current_url, html):
            if self.manual_antibot:
                html_after_manual = self._wait_for_manual_antibot_resolution()
                if html_after_manual is not None:
                    return html_after_manual
            sleep_seconds = self._with_jitter(self.blocked_cooldown_seconds)
            logger.warning("Stage[acquire] selenium_antibot_detected cooldown=%.2fs url=%s", sleep_seconds, current_url)
            time.sleep(sleep_seconds)
            raise AntiBotDetectedError(f"Blocked by Google anti-bot page: {self.driver.current_url}")

        return html

    def _wait_for_manual_antibot_resolution(self) -> str | None:
        if self.headless:
            logger.warning("Stage[acquire] manual_antibot_ignored reason=headless_browser")
            return None

        start_time = time.time()
        logger.warning(
            (
                "Stage[acquire] manual_antibot_wait start timeout=%.1fs poll=%.1fs "
                "action=solve_captcha_in_browser_then_wait"
            ),
            self.manual_antibot_timeout_seconds,
            self.manual_antibot_poll_seconds,
        )
        while time.time() - start_time < self.manual_antibot_timeout_seconds:
            current_url = (self.driver.current_url or "").lower()
            html = self.driver.page_source or ""
            if not is_antibot_page(current_url, html):
                logger.info("Stage[acquire] manual_antibot_resolved elapsed=%.1fs", time.time() - start_time)
                return html
            time.sleep(max(0.2, self.manual_antibot_poll_seconds))

        logger.warning(
            "Stage[acquire] manual_antibot_timeout elapsed=%.1fs",
            time.time() - start_time,
        )
        return None

    def _with_jitter(self, seconds: float) -> float:
        spread = max(seconds * self.jitter_ratio, 0.0)
        return max(0.1, random.uniform(seconds - spread, seconds + spread))
