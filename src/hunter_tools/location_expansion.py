"""Fast location expansion lookups from local JSON mapping."""

from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path


def _mapping_path() -> Path:
    return Path(__file__).with_name("location_expansion.json")


@lru_cache(maxsize=1)
def _load_mapping() -> dict[str, list[str]]:
    path = _mapping_path()
    if not path.exists():
        return {}
    data = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        return {}

    parsed: dict[str, list[str]] = {}
    for key, value in data.items():
        if not isinstance(value, list):
            continue
        terms = [str(item).strip() for item in value if str(item).strip()]
        if terms:
            parsed[str(key).strip().lower()] = terms
    return parsed


def expand_location(location: str) -> list[str]:
    mapping = _load_mapping()
    key = (location or "").strip().lower()
    if key in mapping:
        return mapping[key]
    return [location]

