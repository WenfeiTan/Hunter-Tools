"""Static configuration and defaults for HRBP MVP."""

from __future__ import annotations

from dataclasses import dataclass

HRBP_TITLES = [
    "HRBP",
    "HR Business Partner",
    "Human Resources Business Partner",
    "People Partner",
    "HR Manager",
    "Senior HR Manager",
    "HR Lead",
    "HR Director",
]

LOCATION_EXPANSION = {
    "Frankfurt": ["Frankfurt", "Germany", "Deutschland"],
    "Berlin": ["Berlin", "Germany"],
    "Munich": ["Munich", "Germany"],
}

LANGUAGE_KEYWORDS = ["Mandarin", "Chinese", "Cantonese"]

HRBP_SKILLS = [
    "employee relations",
    "talent management",
    "organizational development",
    "performance management",
    "labor law",
    "recruitment",
    "compensation and benefits",
    "HR strategy",
]

DEFAULT_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/124.0.0.0 Safari/537.36"
    ),
    "Accept-Language": "en-US,en;q=0.9",
}

LINKEDIN_PROFILE_MARKER = "linkedin.com/in/"
BLOCKED_LINKEDIN_PATHS = ("/company/", "/jobs/", "/posts/")

CSV_COLUMNS = [
    "name",
    "profile_url",
    "title",
    "snippet",
    "score",
    "matched_keywords",
    "location_guess",
    "source_query",
    "timestamp",
]


def map_seniority(yoe: int) -> list[str]:
    """Map years of experience to expected seniority titles."""
    if yoe <= 3:
        return ["HR Specialist", "HR Generalist"]
    if yoe <= 7:
        return ["HR Manager", "HRBP"]
    return ["Senior HRBP", "HR Director", "Head of HR"]


@dataclass(frozen=True)
class ScoreWeights:
    title_match: int = 3
    location_match: int = 2
    language_match: int = 2
    skill_match: int = 1

