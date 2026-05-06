"""Dynamic scoring logic driven by score_dictionary/<job>.yaml and score_filter.yaml."""

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
        raise ValueError("Invalid score_filter.yaml: 'weights' must be a dictionary.")

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
        raise ValueError("Invalid score_filter.yaml: 'mode' must be a dictionary.")
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
    score_file = _project_root() / "score_filter.yaml"
    settings = Dynaconf(settings_files=[str(score_file)], environments=False, load_dotenv=False)
    return _parse_weights(settings.get("weights")), _parse_modes(settings.get("mode"))


def load_enabled_filter_dimensions() -> list[str]:
    score_file = _project_root() / "score_filter.yaml"
    settings = Dynaconf(settings_files=[str(score_file)], environments=False, load_dotenv=False)
    raw_filter = settings.get("filter")
    if not isinstance(raw_filter, dict):
        return []

    normalized = _normalize_dict_keys(raw_filter)
    enabled = [dim for dim, value in normalized.items() if bool(value)]
    return enabled


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
            "Score dimensions mismatch between score_dictionary and score_filter.yaml. "
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
        "dict of sub-dimensions."
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


def _extract_guessed_yoe(text: str) -> int | None:
    from hunter_tools.parser import guess_yoe

    guessed = guess_yoe(text)
    if not guessed:
        return None
    try:
        return int(guessed)
    except ValueError:
        return None


def _parse_yoe_token(term: str) -> tuple[int, int] | None:
    token = term.strip().lower()
    bounded = re.match(r"^yoe:(\d+)\s*-\s*(\d+)$", token)
    if bounded:
        start = int(bounded.group(1))
        end = int(bounded.group(2))
        if start > end:
            return None
        return start, end

    lower_bounded = re.match(r"^yoe:(\d+)\s*\+$", token)
    if lower_bounded:
        start = int(lower_bounded.group(1))
        return start, 99
    return None


def _collect_seniority_hits(terms: list[str], merged: str, guessed_yoe: int | None) -> list[str]:
    hits: list[str] = []
    for term in terms:
        token_range = _parse_yoe_token(term)
        if token_range is not None:
            if guessed_yoe is None:
                continue
            start, end = token_range
            if start <= guessed_yoe <= end:
                hits.append(term)
            continue
        if term and term.lower() in merged:
            hits.append(term)
    return hits


def _resolve_terms_for_dimension(context: ScoringContext, dim: str) -> tuple[list[str], str | None]:
    raw = context.rules[dim]
    terms = list(raw or [])
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


def _score_dict_dimension(
    context: ScoringContext,
    dim: str,
    merged: str,
    guessed_yoe: int | None = None,
) -> tuple[int, list[str], dict[str, Any]]:
    mode = context.modes[dim]
    raw = context.rules[dim]
    assert isinstance(raw, dict)

    sub_results: list[dict[str, Any]] = []
    all_hits: list[str] = []
    for sub_dim, sub_terms in raw.items():
        terms = list(sub_terms or [])
        evidence_hits = (
            _collect_seniority_hits(terms, merged, guessed_yoe)
            if dim == "seniority"
            else _collect_hits(terms, merged)
        )
        if not evidence_hits:
            continue
        all_hits.extend(evidence_hits)
        weight = _resolve_weight_for_dimension(context, dim, sub_dim)
        # Seniority is scored once per matched sub-dimension; token+keyword in the
        # same bucket are evidence, not extra scoring hits.
        effective_hit_count = 1 if dim == "seniority" else len(evidence_hits)
        delta = weight if mode == "once" else weight * effective_hit_count
        sub_results.append(
            {
                "sub_dim": sub_dim,
                "weight": weight,
                "hit_count": effective_hit_count,
                "hits": evidence_hits,
                "delta": delta,
            }
        )

    if not sub_results:
        return 0, [], {"sub_dim": None, "weight": context.weights[dim], "mode": mode, "hit_count": 0, "hits": [], "delta": 0}

    if mode == "once":
        chosen = max(sub_results, key=lambda item: (item["delta"], item["hit_count"]))
        return chosen["delta"], chosen["hits"], {
            "sub_dim": chosen["sub_dim"],
            "weight": chosen["weight"],
            "mode": mode,
            "hit_count": chosen["hit_count"],
            "hits": chosen["hits"],
            "delta": chosen["delta"],
        }

    total_delta = sum(int(item["delta"]) for item in sub_results)
    unique_hits = list(dict.fromkeys(all_hits))
    total_hit_count = len(sub_results) if dim == "seniority" else len(unique_hits)
    return total_delta, unique_hits, {
        "sub_dim": "multi",
        "weight": "mixed",
        "mode": mode,
        "hit_count": total_hit_count,
        "hits": unique_hits,
        "delta": total_delta,
        "sub_breakdown": sub_results,
    }


def score_text(
    text: str,
    context: ScoringContext,
    location_text: str = "",
) -> tuple[int, list[str], dict[str, dict[str, Any]]]:
    merged = lower_text(text)
    location_merged = lower_text(location_text)
    guessed_yoe = _extract_guessed_yoe(text)
    total = 0
    reasons: list[str] = []
    breakdown: dict[str, dict[str, Any]] = {}

    for dim in context.weights:
        if isinstance(context.rules[dim], dict):
            delta, hits, dim_breakdown = _score_dict_dimension(context, dim, merged, guessed_yoe=guessed_yoe)
            total += delta
            reasons.extend([f"{dim}:{term}" for term in hits])
            breakdown[dim] = dim_breakdown
            continue

        terms, sub_dim = _resolve_terms_for_dimension(context, dim)
        weight = _resolve_weight_for_dimension(context, dim, sub_dim)
        dim_merged = location_merged if dim == "location" else merged
        hits = _collect_hits(terms, dim_merged)
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
