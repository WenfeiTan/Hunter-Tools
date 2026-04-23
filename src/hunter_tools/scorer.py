"""Candidate scoring rules for MVP."""

from __future__ import annotations

from hunter_tools.config import HRBP_SKILLS, LANGUAGE_KEYWORDS, ScoreWeights, map_seniority
from hunter_tools.utils import lower_text


def _collect_hits(candidates: list[str], merged: str) -> list[str]:
    return [term for term in candidates if term and term.lower() in merged]


def score_text(
    text: str,
    location_terms: list[str],
    yoe: int,
    job_title: str,
    custom_keywords: list[str] | None = None,
    weights: ScoreWeights | None = None,
) -> tuple[int, list[str]]:
    weights = weights or ScoreWeights()
    merged = lower_text(text)
    score = 0
    hits: list[str] = []

    title_terms = [job_title, "HRBP", "HR Business Partner", "Human Resources Business Partner"]
    title_hits = _collect_hits(title_terms, merged)
    if title_hits:
        score += weights.title_match
        hits.extend(title_hits)

    if any(location.lower() in merged for location in location_terms):
        score += weights.location_match
        hits.append("location")

    language_hits = _collect_hits(LANGUAGE_KEYWORDS, merged)
    if language_hits:
        score += weights.language_match
        hits.extend(language_hits)

    seniority_hits = _collect_hits(map_seniority(yoe), merged)
    if seniority_hits:
        score += 2
        hits.extend(seniority_hits)

    for skill in HRBP_SKILLS:
        if skill.lower() in merged:
            score += weights.skill_match
            hits.append(skill)

    for custom in custom_keywords or []:
        if custom and custom.lower() in merged:
            score += 2
            hits.append(custom)

    unique_hits = list(dict.fromkeys(hits))
    return score, unique_hits
