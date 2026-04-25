"""Build Google X-Ray queries."""

from __future__ import annotations

import logging
import re
from pathlib import Path

from dynaconf import Dynaconf

from hunter_tools.location_expansion import expand_location
from hunter_tools.models import SearchInput

logger = logging.getLogger(__name__)


def _or_group(items: list[str], quoted: bool = True) -> str:
    if not items:
        return ""
    values = [f'"{item}"' if quoted else item for item in items]
    if len(values) == 1:
        return values[0]
    return f"({' OR '.join(values)})"


def _slugify(text: str) -> str:
    normalized = re.sub(r"[^a-z0-9]+", "_", text.strip().lower())
    normalized = normalized.strip("_")
    return normalized or "unknown"


def _load_title_aliases(job_title: str) -> list[str]:
    project_root = Path(__file__).resolve().parents[2]
    dictionary_path = project_root / "score_dictionary" / f"{_slugify(job_title)}.yaml"
    if not dictionary_path.exists():
        logger.warning("Stage[query] score_dictionary_not_found job_title=%s path=%s", job_title, dictionary_path)
        return [job_title]

    settings = Dynaconf(settings_files=[str(dictionary_path)], environments=False, load_dotenv=False)
    title_terms = settings.get("title")
    if not isinstance(title_terms, list) or not title_terms:
        logger.warning(
            "Stage[query] invalid_title_dimension job_title=%s path=%s fallback_to_job_title",
            job_title,
            dictionary_path,
        )
        return [job_title]

    deduped = []
    seen = set()
    for term in title_terms:
        normalized = str(term).strip()
        key = normalized.lower()
        if normalized and key not in seen:
            deduped.append(normalized)
            seen.add(key)
    return deduped or [job_title]


def _title_terms(search_input: SearchInput) -> tuple[list[str], list[str]]:
    base_title = search_input.job_title.strip() or "unknown"
    dictionary_titles = _load_title_aliases(base_title)
    aliases = [title for title in dictionary_titles if title.lower() != base_title.lower()]
    mode = search_input.title_alias_mode

    if mode == "off":
        core = [base_title]
        broad = [base_title]
    elif mode == "broad":
        core = [base_title] + aliases[:3]
        broad = [base_title] + aliases[:6]
    else:
        core = [base_title] + aliases[:2]
        broad = [base_title] + aliases[:4]

    return list(dict.fromkeys(core)), list(dict.fromkeys(broad))


def _location_terms(search_input: SearchInput) -> tuple[list[str], list[str]]:
    expanded = expand_location(search_input.location)
    mode = search_input.location_mode

    if mode == "strict":
        return [search_input.location], [search_input.location]
    if mode == "country_only":
        country = expanded[-1:]
        return country, country
    core_locations = expanded[:2] if len(expanded) > 1 else expanded
    country_fallback = expanded[-1:]
    return core_locations, country_fallback


def build_queries(search_input: SearchInput) -> list[str]:
    core_titles, broad_titles = _title_terms(search_input)
    core_locations, country_fallback = _location_terms(search_input)
    search_terms = [term.strip() for term in search_input.search_args if term.strip()]

    # Query 1: highest recall, avoid skill/language constraints.
    high_recall_parts = [
        "site:linkedin.com/in",
        _or_group(core_titles),
        _or_group(core_locations),
    ]
    if search_terms:
        # search_args only affect the shortest baseline query and never scoring.
        high_recall_parts.append(_or_group(search_terms))
    high_recall_parts.append("-jobs -hiring -recruiter")
    high_recall_query = " ".join(high_recall_parts)

    # Query 2: broader title coverage with only region-level location.
    region_query = " ".join(
        [
            "site:linkedin.com/in",
            _or_group(broad_titles),
            _or_group(country_fallback),
            "-jobs -hiring -recruiter",
        ]
    )

    # Query 3: title only fallback to recover from strict geo filtering.
    title_only_query = " ".join(
        [
            "site:linkedin.com/in",
            _or_group(core_titles),
            "-jobs -hiring -recruiter",
        ]
    )

    queries = [high_recall_query]

    if country_fallback != core_locations:
        queries.append(region_query)

    # If strict location + no aliases, title-only fallback usually too broad; skip it.
    if not (search_input.location_mode == "strict" and search_input.title_alias_mode == "off"):
        queries.append(title_only_query)

    return list(dict.fromkeys(queries))
