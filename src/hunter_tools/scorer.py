"""Dynamic scoring logic driven by score_dictionary/<job>.yaml and score.yaml."""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from dynaconf import Dynaconf

from hunter_tools.utils import lower_text


@dataclass(frozen=True)
class ScoringContext:
    weights: dict[str, int | list[int]]
    modes: dict[str, str]
    rules: dict[str, Any]
    runtime_location_terms: list[str]


def _project_root() -> Path:
    return Path(__file__).resolve().parents[2]


def _slugify(text: str) -> str:
    normalized = re.sub(r"[^a-z0-9]+", "_", text.strip().lower())
    normalized = normalized.strip("_")
    return normalized or "unknown"


def _normalize_dict_keys(value: Any) -> Any:
    if isinstance(value, dict):
        return {str(key).lower(): _normalize_dict_keys(val) for key, val in value.items()}
    if isinstance(value, list):
        return [_normalize_dict_keys(item) for item in value]
    return value


def _clean_dynaconf_meta(data: dict[str, Any]) -> dict[str, Any]:
    return {
        key: value
        for key, value in data.items()
        if not key.startswith("dynaconf") and key != "load_dotenv"
    }


def _parse_weights(raw_weights: Any) -> dict[str, int | list[int]]:
    if not isinstance(raw_weights, dict):
        raise ValueError("Invalid score.yaml: 'weights' must be a dictionary.")

    normalized = _normalize_dict_keys(raw_weights)
    parsed: dict[str, int | list[int]] = {}
    for dimension, weight in normalized.items():
        if isinstance(weight, list):
            converted: list[int] = []
            for item in weight:
                try:
                    converted.append(int(item))
                except (TypeError, ValueError) as exc:
                    raise ValueError(f"Invalid list weight item for dimension '{dimension}': {item}") from exc
            parsed[str(dimension)] = converted
            continue
        try:
            parsed[str(dimension)] = int(weight)
        except (TypeError, ValueError) as exc:
            raise ValueError(f"Invalid weight for dimension '{dimension}': {weight}") from exc
    return parsed


def _parse_modes(raw_modes: Any) -> dict[str, str]:
    if not isinstance(raw_modes, dict):
        raise ValueError("Invalid score.yaml: 'mode' must be a dictionary.")
    normalized = _normalize_dict_keys(raw_modes)
    allowed_modes = {"once", "per_hit"}
    parsed: dict[str, str] = {}
    for dimension, mode in normalized.items():
        mode_text = str(mode).lower()
        if mode_text not in allowed_modes:
            raise ValueError(
                f"Invalid mode for dimension '{dimension}': {mode}. "
                f"Allowed values: {sorted(allowed_modes)}"
            )
        parsed[str(dimension)] = mode_text
    return parsed


def _load_score_config() -> tuple[dict[str, int | list[int]], dict[str, str]]:
    score_file = _project_root() / "score.yaml"
    settings = Dynaconf(settings_files=[str(score_file)], environments=False, load_dotenv=False)
    return _parse_weights(settings.get("weights")), _parse_modes(settings.get("mode"))


def _load_score_dictionary(job_title: str) -> dict[str, Any]:
    dictionary_dir = _project_root() / "score_dictionary"
    slug = _slugify(job_title)
    dictionary_path = dictionary_dir / f"{slug}.yaml"
    if not dictionary_path.exists():
        raise FileNotFoundError(
            f"Score dictionary not found for job title '{job_title}'. "
            f"Expected file: {dictionary_path}. Please create it before scoring."
        )

    settings = Dynaconf(settings_files=[str(dictionary_path)], environments=False, load_dotenv=False)
    raw = settings.as_dict()
    if not isinstance(raw, dict):
        raise ValueError(f"Invalid score dictionary: {dictionary_path}")
    return _clean_dynaconf_meta(_normalize_dict_keys(raw))


def _validate_dimensions(
    score_rules: dict[str, Any],
    score_weights: dict[str, int | list[int]],
    score_modes: dict[str, str],
) -> None:
    rule_dims = set(score_rules.keys())
    weight_dims = set(score_weights.keys())
    mode_dims = set(score_modes.keys())
    if not (rule_dims == weight_dims == mode_dims):
        raise ValueError(
            "Score dimensions mismatch between score_dictionary and score.yaml. "
            f"dictionary={sorted(rule_dims)} weights={sorted(weight_dims)} mode={sorted(mode_dims)}"
        )
    if not rule_dims:
        raise ValueError("Scoring dimensions cannot be empty.")

    for dim, rule_value in score_rules.items():
        weight_value = score_weights[dim]
        if isinstance(rule_value, dict):
            if isinstance(weight_value, list):
                if len(weight_value) != len(rule_value.keys()):
                    raise ValueError(
                        f"Weight mismatch for dimension '{dim}': list length={len(weight_value)} "
                        f"but sub-dimensions={len(rule_value.keys())}"
                    )
            elif not isinstance(weight_value, int):
                raise ValueError(
                    f"Invalid weight type for dimension '{dim}'. "
                    "Expected int or list[int] when rule is dict."
                )
        elif isinstance(rule_value, list):
            if isinstance(weight_value, list):
                raise ValueError(
                    f"Invalid weight type for dimension '{dim}'. "
                    "list[int] is only allowed for dict rule dimensions."
                )
            if not isinstance(weight_value, int):
                raise ValueError(
                    f"Invalid weight type for dimension '{dim}'. Expected int when rule is list."
                )


def _validate_rule_value(dim: str, value: Any) -> None:
    if isinstance(value, list):
        return
    if isinstance(value, dict):
        if not value:
            raise ValueError(f"Invalid banded dimension '{dim}': empty dict is not allowed.")
        for band, band_terms in value.items():
            if not isinstance(band_terms, list):
                raise ValueError(f"Invalid band list for '{dim}.{band}'. Must be list[str].")
        return
    raise ValueError(
        f"Invalid rule type for dimension '{dim}'. Expected list[str] or "
        "banded dict {'junior','mid','senior'}."
    )


def load_scoring_context(
    job_title: str,
    location_terms: list[str],
) -> ScoringContext:
    score_rules = _load_score_dictionary(job_title)
    score_weights, score_modes = _load_score_config()
    _validate_dimensions(score_rules, score_weights, score_modes)
    for dim, value in score_rules.items():
        _validate_rule_value(dim, value)

    return ScoringContext(
        weights=score_weights,
        modes=score_modes,
        rules=score_rules,
        runtime_location_terms=location_terms,
    )


def _collect_hits(candidates: list[str], merged: str) -> list[str]:
    return [term for term in candidates if term and term.lower() in merged]


def _seniority_band(yoe: int) -> str:
    if yoe <= 3:
        return "junior"
    if yoe <= 7:
        return "mid"
    return "senior"


def _resolve_terms_for_dimension(context: ScoringContext, dim: str, yoe: int) -> tuple[list[str], str | None]:
    raw = context.rules[dim]
    if isinstance(raw, dict):
        band = _seniority_band(yoe)
        if band in raw:
            terms = list(raw[band] or [])
            return terms, band
        first_key = next(iter(raw.keys()))
        terms = list(raw[first_key] or [])
        return terms, first_key
    else:
        terms = list(raw or [])
    if dim == "location":
        terms = list(dict.fromkeys([*terms, *context.runtime_location_terms]))
    return terms, None


def _resolve_weight_for_dimension(
    context: ScoringContext,
    dim: str,
    sub_dim: str | None,
) -> int:
    raw_weight = context.weights[dim]
    if isinstance(raw_weight, int):
        return raw_weight
    if sub_dim is None:
        raise ValueError(
            f"Invalid weight config for dimension '{dim}': list[int] requires dict rule with active sub-dimension."
        )
    ordered_sub_dims = list(context.rules[dim].keys())
    index = ordered_sub_dims.index(sub_dim)
    return raw_weight[index]


def score_text(text: str, yoe: int, context: ScoringContext) -> tuple[int, list[str]]:
    merged = lower_text(text)
    total = 0
    reasons: list[str] = []
    breakdown: dict[str, dict[str, Any]] = {}

    for dim in context.weights:
        terms, sub_dim = _resolve_terms_for_dimension(context, dim, yoe)
        weight = _resolve_weight_for_dimension(context, dim, sub_dim)
        hits = _collect_hits(terms, merged)
        if not hits:
            breakdown[dim] = {
                "sub_dim": sub_dim,
                "weight": weight,
                "mode": context.modes[dim],
                "hit_count": 0,
                "hits": [],
                "delta": 0,
            }
            continue

        if context.modes[dim] == "once":
            delta = weight
        else:
            delta = weight * len(hits)

        total += delta

        reasons.extend([f"{dim}:{term}" for term in hits])
        breakdown[dim] = {
            "sub_dim": sub_dim,
            "weight": weight,
            "mode": context.modes[dim],
            "hit_count": len(hits),
            "hits": hits,
            "delta": delta,
        }

    return total, list(dict.fromkeys(reasons)), breakdown
