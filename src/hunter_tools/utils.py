"""Reusable utility functions."""

from __future__ import annotations

import re
from urllib.parse import parse_qs, urlparse


def normalize_text(text: str) -> str:
    return re.sub(r"\s+", " ", text or "").strip()


def lower_text(text: str) -> str:
    return normalize_text(text).lower()


def unwrap_google_redirect(url: str) -> str:
    """Extract the real URL from Google '/url?q=...' links if present."""
    parsed = urlparse(url)
    if parsed.path != "/url":
        return url
    query = parse_qs(parsed.query)
    return query.get("q", [url])[0]

