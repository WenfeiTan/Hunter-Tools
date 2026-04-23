"""End-to-end orchestration for sourcing pipeline."""

from __future__ import annotations

import logging
from typing import Protocol

from hunter_tools.config import LOCATION_EXPANSION
from hunter_tools.models import Candidate, SearchInput
from hunter_tools.parser import extract_name, filter_profile_results, guess_location, normalize_profile_url
from hunter_tools.query_builder import build_queries
from hunter_tools.scorer import score_text
from hunter_tools.selenium_client import SeleniumGoogleClient

logger = logging.getLogger(__name__)


class SearchClient(Protocol):
    def search(self, query: str, pages: int = 2, page_size: int = 10, delay_seconds: float = 1.5): ...


def run_pipeline(
    search_input: SearchInput, client: SearchClient | None = None, fail_fast: bool = False
) -> tuple[list[str], list[Candidate]]:
    logger.info(
        "Stage[pipeline] start job_title=%s location=%s yoe=%s pages_per_query=%s page_size=%s",
        search_input.job_title,
        search_input.location,
        search_input.yoe,
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
    location_terms = LOCATION_EXPANSION.get(search_input.location, [search_input.location])

    logger.info("Stage[score] start dedupe+scoring")
    by_profile: dict[str, Candidate] = {}
    for result in filtered:
        profile_url = normalize_profile_url(result.link)
        full_text = f"{result.title} {result.snippet}"
        score, matched_keywords = score_text(
            full_text,
            location_terms=location_terms,
            yoe=search_input.yoe,
            job_title=search_input.job_title,
            score_keywords=search_input.score_args,
        )

        candidate = Candidate(
            name=extract_name(result.title),
            profile_url=profile_url,
            title=result.title,
            snippet=result.snippet,
            score=score,
            matched_keywords=matched_keywords,
            location_guess=guess_location(result.snippet, location_terms),
            source_query=result.query,
        )
        logger.info(
            "Stage[score] candidate_scored name=%s profile_url=%s score=%s reasons=%s source_query=%s",
            candidate.name,
            candidate.profile_url,
            candidate.score,
            candidate.matched_keywords,
            candidate.source_query,
        )

        existing = by_profile.get(profile_url)
        if existing is None or candidate.score > existing.score:
            if existing is not None:
                logger.info(
                    "Stage[score] candidate_replaced profile_url=%s old_score=%s new_score=%s",
                    profile_url,
                    existing.score,
                    candidate.score,
                )
            by_profile[profile_url] = candidate

    logger.info("Stage[score] unique_profiles=%s", len(by_profile))
    ranked = sorted(by_profile.values(), key=lambda item: item.score, reverse=True)
    logger.info("Stage[rank] done ranked_candidates=%s", len(ranked))
    if not ranked:
        logger.warning(
            "Stage[rank] empty_output reason=no_ranked_candidates raw_results=%s filtered_results=%s",
            len(all_results),
            len(filtered),
        )
    return queries, ranked
