"""Domain models used across modules."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone


@dataclass(frozen=True)
class SearchInput:
    job_title: str
    location: str
    yoe: int
    score_args: list[str] = field(default_factory=list)
    search_args: list[str] = field(default_factory=list)
    title_alias_mode: str = "core"
    location_mode: str = "expanded"
    pages_per_query: int = 2
    page_size: int = 10
    delay_seconds: float = 1.5


@dataclass(frozen=True)
class SearchResult:
    title: str
    link: str
    snippet: str
    query: str


@dataclass
class Candidate:
    name: str
    profile_url: str
    title: str
    snippet: str
    score: int
    matched_keywords: list[str]
    location_guess: str
    source_query: str
    timestamp: str = field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat(timespec="seconds")
    )

    def to_row(self) -> dict[str, str | int]:
        return {
            "name": self.name,
            "profile_url": self.profile_url,
            "title": self.title,
            "snippet": self.snippet,
            "score": self.score,
            "matched_keywords": ", ".join(self.matched_keywords),
            "location_guess": self.location_guess,
            "source_query": self.source_query,
            "timestamp": self.timestamp,
        }
