"""Result parsing and filtering logic."""

from __future__ import annotations

import re
from urllib.parse import urlparse

from hunter_tools.models import SearchResult
from hunter_tools.utils import normalize_text, unwrap_google_redirect

LINKEDIN_PROFILE_MARKER = "linkedin.com/in/"
BLOCKED_LINKEDIN_PATHS = ("/company/", "/jobs/", "/posts/")
LOCATION_PREFIX_RE = re.compile(r"^(?:location|based in|所在地|现居地|地区|位置)\s*[:：]\s*", re.IGNORECASE)
LOCATION_ADMIN_MARKERS = (
    " area",
    " region",
    " metropolitan",
    " metro",
    " province",
    " state",
    " county",
    " city",
    " district",
    " prefecture",
    " canton",
    "市",
    "省",
    "区",
    "县",
    "州",
    "地区",
)
LOCATION_COUNTRY_MARKERS = (
    "china",
    "germany",
    "deutschland",
    "united states",
    "usa",
    "united kingdom",
    "uk",
    "england",
    "france",
    "spain",
    "italy",
    "netherlands",
    "switzerland",
    "sweden",
    "singapore",
    "japan",
    "canada",
    "australia",
    "india",
    "中国",
    "德国",
    "英国",
    "美国",
)
NON_LOCATION_PATTERNS = (
    r"https?://",
    r"www\.",
    r"@",
    r"\b\d{1,2}\+?\s*(?:years?|yrs?)\b",
    "工作经历",
    "教育经历",
    "linkedin",
    "profile",
)


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


def _current_location_segment(snippet: str) -> str:
    # LinkedIn snippets commonly start with the current location before "·".
    # Example: "Frankfurt, Hesse, Germany · HR Business Partner · ..."
    first_line = re.split(r"[\r\n]", snippet, maxsplit=1)[0]
    segment = re.split(r"\s+[·•]\s+", first_line, maxsplit=1)[0].strip()
    return LOCATION_PREFIX_RE.sub("", segment).strip()


def _looks_like_location_segment(segment: str, known_locations: list[str] | None = None) -> bool:
    if not segment:
        return False
    if len(segment) > 80:
        return False
    lowered = segment.lower()
    if any(re.search(pattern, lowered) for pattern in NON_LOCATION_PATTERNS):
        return False
    if known_locations and any(location.lower() in lowered for location in known_locations if location):
        return True
    if any(marker in lowered for marker in LOCATION_COUNTRY_MARKERS):
        return True
    if any(marker in lowered for marker in LOCATION_ADMIN_MARKERS):
        return True
    return False


def guess_location(snippet: str, known_locations: list[str]) -> str:
    current_location = _current_location_segment(snippet)
    if _looks_like_location_segment(current_location, known_locations):
        return normalize_text(current_location)
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
