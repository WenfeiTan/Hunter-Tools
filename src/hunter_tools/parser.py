"""Result parsing and filtering logic."""

from __future__ import annotations

import re
from urllib.parse import urlparse

from hunter_tools.models import SearchResult
from hunter_tools.utils import normalize_text, unwrap_google_redirect

LINKEDIN_PROFILE_MARKER = "linkedin.com/in/"
BLOCKED_LINKEDIN_PATHS = ("/company/", "/jobs/", "/posts/")


def is_valid_linkedin_profile(url: str) -> bool:
    raw = unwrap_google_redirect(url)
    lowered = raw.lower()
    if LINKEDIN_PROFILE_MARKER not in lowered:
        return False
    return not any(path in lowered for path in BLOCKED_LINKEDIN_PATHS)


def normalize_profile_url(url: str) -> str:
    candidate = unwrap_google_redirect(url)
    parsed = urlparse(candidate)
    if not parsed.scheme:
        return candidate
    clean_path = parsed.path.rstrip("/")
    return f"{parsed.scheme}://{parsed.netloc}{clean_path}"


def extract_name(title: str) -> str:
    # Google title often looks like "Name - Role | LinkedIn"
    cleaned = re.split(r"\s+[\-|–|•|·]\s+", title, maxsplit=1)[0]
    return normalize_text(cleaned)


def guess_location(snippet: str, known_locations: list[str]) -> str:
    snippet_low = snippet.lower()
    for location in known_locations:
        if location.lower() in snippet_low:
            return location
    return ""


def guess_yoe(text: str) -> str:
    # Capture "13 years", "5+ yrs", and common Chinese forms like "3年经验".
    patterns = [
        r"\b(\d{1,2})\+?\s*(?:years?|yrs?)\b",
        r"(\d{1,2})\s*(?:年以上|年经验|年)",
    ]
    found: list[int] = []
    for pattern in patterns:
        found.extend(int(value) for value in re.findall(pattern, text, flags=re.IGNORECASE))
    if not found:
        return ""
    return str(max(found))


def filter_profile_results(results: list[SearchResult]) -> list[SearchResult]:
    return [result for result in results if is_valid_linkedin_profile(result.link)]
