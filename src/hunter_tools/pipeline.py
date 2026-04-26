"""End-to-end orchestration for sourcing pipeline."""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import Protocol

from hunter_tools.exporter import export_middle_to_csv, load_middle_from_csv
from hunter_tools.location_expansion import expand_location
from hunter_tools.models import Candidate, SearchInput, SearchResult
from hunter_tools.parser import extract_name, filter_profile_results, guess_location, guess_yoe, normalize_profile_url
from hunter_tools.query_builder import build_queries
from hunter_tools.scorer import load_scoring_context, score_text
from hunter_tools.selenium_client import SeleniumGoogleClient
from hunter_tools.settings import load_settings

logger = logging.getLogger(__name__)
settings = load_settings()


class SearchClient(Protocol):
    def search(self, query: str, pages: int = 2, page_size: int = 10, delay_seconds: float = 1.5): ...


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _middle_output_path(output_csv_path: str | None, job_title: str) -> Path:
    middle_dir = Path(str(settings.get("middle_output_dir", "outputs/middle")))
    if output_csv_path:
        return middle_dir / Path(output_csv_path).name
    slug = "".join(char.lower() if char.isalnum() else "_" for char in job_title).strip("_") or "unknown"
    return middle_dir / f"{slug}.csv"


def _build_middle_rows(results: list[SearchResult], location_terms: list[str]) -> list[dict[str, str]]:
    deduped: dict[str, dict[str, str]] = {}
    for result in results:
        profile_url = normalize_profile_url(result.link)
        if profile_url in deduped:
            continue
        deduped[profile_url] = {
            "name": extract_name(result.title),
            "profile_url": profile_url,
            "title": result.title,
            "snippet": result.snippet,
            "location_guess": guess_location(result.snippet, location_terms),
            "yoe_guess": guess_yoe(f"{result.title} {result.snippet}"),
            "source_query": result.query,
            "timestamp": _now_iso(),
        }
    return list(deduped.values())


def _score_middle_rows(search_input: SearchInput, middle_rows: list[dict[str, str]]) -> list[Candidate]:
    location_terms = expand_location(search_input.location, expand_level=search_input.location_expand_level)
    scoring_context = load_scoring_context(
        job_title=search_input.job_title,
        location_terms=location_terms,
    )

    candidates: list[Candidate] = []
    for row in middle_rows:
        full_text = f"{row.get('title', '')} {row.get('snippet', '')}"
        score, matched_keywords, breakdown = score_text(
            text=full_text,
            context=scoring_context,
        )
        candidate = Candidate(
            name=row.get("name", ""),
            profile_url=row.get("profile_url", ""),
            title=row.get("title", ""),
            snippet=row.get("snippet", ""),
            score=score,
            matched_keywords=matched_keywords,
            location_guess=row.get("location_guess", ""),
            yoe_guess=row.get("yoe_guess", row.get("guess_yoe", "")),
            source_query=row.get("source_query", ""),
            timestamp=row.get("timestamp", _now_iso()),
        )
        logger.info(
            (
                "Stage[score] candidate_scored name=%s profile_url=%s score=%s "
                "reasons=%s breakdown=%s source_query=%s"
            ),
            candidate.name,
            candidate.profile_url,
            candidate.score,
            candidate.matched_keywords,
            breakdown,
            candidate.source_query,
        )
        candidates.append(candidate)

    ranked = sorted(candidates, key=lambda item: item.score, reverse=True)
    logger.info("Stage[rank] done ranked_candidates=%s", len(ranked))
    if not ranked:
        logger.warning("Stage[rank] empty_output reason=no_ranked_candidates middle_rows=%s", len(middle_rows))
    return ranked


def run_pipeline(
    search_input: SearchInput,
    client: SearchClient | None = None,
    fail_fast: bool = False,
    output_csv_path: str | None = None,
) -> tuple[list[str], list[Candidate]]:
    logger.info(
        "Stage[pipeline] start job_title=%s location=%s pages_per_query=%s page_size=%s",
        search_input.job_title,
        search_input.location,
        search_input.pages_per_query,
        search_input.page_size,
    )
    google_client = client or SeleniumGoogleClient()

    logger.info("Stage[query] building queries")
    queries = build_queries(search_input)
    for idx, query in enumerate(queries, start=1):
        logger.info("Stage[query] query_%s=%s", idx, query)

    logger.info("Stage[acquire] executing query batch size=%s", len(queries))
    all_results = []
    for query in queries:
        try:
            query_results = google_client.search(
                query=query,
                pages=search_input.pages_per_query,
                page_size=search_input.page_size,
                delay_seconds=search_input.delay_seconds,
            )
            all_results.extend(query_results)
            logger.info("Stage[acquire] query_done results=%s query=%s", len(query_results), query)
        except Exception as exc:  # pylint: disable=broad-except
            if fail_fast:
                logger.exception("Stage[acquire] query_failed fail_fast=true query=%s", query)
                raise
            logger.warning("Stage[acquire] query_failed_skipped query=%s reason=%s", query, exc)

    logger.info("Stage[parse] filtering linkedin profile urls raw_results=%s", len(all_results))
    filtered = filter_profile_results(all_results)
    logger.info("Stage[parse] filtered_results=%s", len(filtered))
    location_terms = expand_location(search_input.location, expand_level=search_input.location_expand_level)

    middle_rows = _build_middle_rows(filtered, location_terms)
    logger.info("Stage[middle] built rows=%s", len(middle_rows))
    if bool(settings.get("middle", True)):
        middle_path = _middle_output_path(output_csv_path=output_csv_path, job_title=search_input.job_title)
        export_middle_to_csv(middle_rows, str(middle_path))
        logger.info("Stage[middle] output_path=%s", middle_path)

    logger.info("Stage[score] start scoring_from_middle rows=%s", len(middle_rows))
    ranked = _score_middle_rows(search_input, middle_rows)
    return queries, ranked


def run_rescore_from_middle(
    search_input: SearchInput,
    middle_csv_path: str,
) -> list[Candidate]:
    logger.info("Stage[rescore] start middle_csv_path=%s", middle_csv_path)
    middle_rows = load_middle_from_csv(middle_csv_path)
    logger.info("Stage[rescore] loaded middle rows=%s", len(middle_rows))
    return _score_middle_rows(search_input, middle_rows)
