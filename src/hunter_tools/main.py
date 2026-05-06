"""CLI entrypoint for Hunter Tools MVP."""

from __future__ import annotations

import argparse
import logging
from datetime import datetime
from pathlib import Path

from hunter_tools.exporter import export_candidates_to_csv
from hunter_tools.models import SearchInput
from hunter_tools.pipeline import run_pipeline, run_rescore_from_middle
from hunter_tools.scorer import load_enabled_filter_dimensions
from hunter_tools.selenium_client import SeleniumGoogleClient
from hunter_tools.settings import load_settings

logger = logging.getLogger(__name__)
settings = load_settings()


def _apply_strong_filter(candidates, enabled_dims: list[str]):
    if not enabled_dims:
        return candidates
    filtered = []
    for candidate in candidates:
        hits = candidate.matched_keywords
        if all(any(hit.startswith(f"{dim}:") for hit in hits) for dim in enabled_dims):
            filtered.append(candidate)
    return filtered


def _derive_filter_output_path(output_path: str) -> str:
    path = Path(output_path)
    suffix = path.suffix or ".csv"
    stem = path.stem if path.suffix else path.name
    filter_name = f"{stem}_filter{suffix}"
    return str(path.with_name(filter_name))


def _normalize_search_args(search_args: list[str]) -> list[str]:
    """
    Break down search_args elements by commas into individual keywords.
    Remove brackets and other extraneous characters.
    
    Examples:
    - ["consultant"] -> ["consultant"]
    - ["consultant, business development"] -> ["consultant", "business development"]
    - ['["solar modules", "invertes"]'] -> ["solar modules", "invertes"]
    """
    if not search_args:
        return []
    
    result = []
    for arg in search_args:
        if not arg or not arg.strip():
            continue
        # Remove brackets, quotes, and other extraneous characters
        cleaned = arg.strip()
        # Remove leading/trailing brackets and quotes
        cleaned = cleaned.strip('[]"\'')
        # Split by comma and strip whitespace from each part
        parts = [part.strip().strip('[]"\'') for part in cleaned.split(",")]
        result.extend([p for p in parts if p])
    return result


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Google X-Ray candidate sourcing MVP")
    parser.add_argument(
        "--config",
        action="store_true",
        help="Use all parameters from config.yaml; skips interactive mode and requires job_title and location in config.",
    )
    parser.add_argument("--job-title", default=str(settings.get("job_title", "")), help="Job title, e.g., HRBP")
    parser.add_argument("--location", default=str(settings.get("location", "")), help="Location, e.g., Frankfurt")
    parser.add_argument(
        "--search-args",
        nargs="*",
        default=list(settings.get("search_args", [])),
        help="Keywords used only in baseline query (comma/space-separated), not in scoring.",
    )
    parser.add_argument(
        "--title-alias-mode",
        choices=["off", "core", "broad"],
        default=str(settings.get("title_alias_mode", "core")),
        help="Control job title alias expansion in query generation.",
    )
    parser.add_argument(
        "--location-mode",
        choices=["strict", "expanded", "country_only"],
        default=str(settings.get("location_mode", "expanded")),
        help="Control location strictness in query generation.",
    )
    parser.add_argument(
        "--location-expand-level",
        type=int,
        default=int(settings.get("location_expand_level", 2)),
        help="Expansion level for location_mode=expanded (1-3).",
    )
    parser.add_argument(
        "--pages-per-query",
        type=int,
        default=int(settings.get("pages_per_query", 1)),
        help="Google pages per query",
    )
    parser.add_argument("--page-size", type=int, default=int(settings.get("page_size", 10)), help="Results per page")
    parser.add_argument(
        "--delay-seconds",
        type=float,
        default=float(settings.get("delay_seconds", 1.5)),
        help="Request interval",
    )
    parser.add_argument(
        "--timeout-seconds",
        type=float,
        default=float(settings.get("timeout_seconds", 25.0)),
        help="Page load timeout in seconds",
    )
    parser.add_argument(
        "--blocked-cooldown-seconds",
        type=float,
        default=float(settings.get("blocked_cooldown_seconds", 25.0)),
        help="Cooldown seconds when anti-bot page is detected",
    )
    parser.add_argument(
        "--jitter-ratio",
        type=float,
        default=float(settings.get("jitter_ratio", 0.35)),
        help="Random jitter ratio for delays",
    )
    parser.add_argument(
        "--fail-fast",
        action=argparse.BooleanOptionalAction,
        default=bool(settings.get("fail_fast", False)),
        help="Stop immediately when one query fails",
    )
    parser.add_argument(
        "--show-browser",
        action=argparse.BooleanOptionalAction,
        default=bool(settings.get("show_browser", False)),
        help="Show browser UI (default is headless).",
    )
    parser.add_argument(
        "--raw-output-dir",
        default=str(settings.get("raw_output_dir", "outputs/raw_pages")),
        help="Directory to persist raw fetched HTML pages before parsing.",
    )
    parser.add_argument(
        "--manual-antibot",
        action=argparse.BooleanOptionalAction,
        default=bool(settings.get("manual_antibot", False)),
        help="Wait for manual captcha solving in visible browser when anti-bot page appears.",
    )
    parser.add_argument(
        "--manual-antibot-timeout-seconds",
        type=float,
        default=float(settings.get("manual_antibot_timeout_seconds", 180.0)),
        help="Max seconds to wait for manual anti-bot solving.",
    )
    parser.add_argument(
        "--manual-antibot-poll-seconds",
        type=float,
        default=float(settings.get("manual_antibot_poll_seconds", 2.0)),
        help="Polling interval while waiting for manual anti-bot solving.",
    )
    parser.add_argument("--interactive", action="store_true", help="Prompt parameters interactively in terminal.")
    parser.add_argument(
        "--rescore-middle-csv",
        default=None,
        help="Path to previously exported middle CSV. If provided, skip search and only rerun scoring.",
    )
    parser.add_argument(
        "--debug",
        action=argparse.BooleanOptionalAction,
        default=bool(settings.get("debug", False)),
        help="Enable debug logging",
    )
    parser.add_argument("--output", default=str(settings.get("output", "outputs/candidates.csv")), help="CSV output path")
    return parser.parse_args()


def _prompt_text(label: str, description: str, default: str | None = None) -> str:
    prompt = f"{label} ({description})"
    if default is not None:
        prompt += f" [default: {default}]"
    prompt += ": "

    while True:
        value = input(prompt).strip()
        if value:
            return value
        if default is not None:
            return default
        print("This field is required.")


def _prompt_int(label: str, description: str, default: int) -> int:
    while True:
        raw = _prompt_text(label, description, str(default))
        try:
            return int(raw)
        except ValueError:
            print("Please enter an integer.")


def _prompt_choice(label: str, description: str, choices: list[str], default: str) -> str:
    choices_text = "/".join(choices)
    while True:
        value = _prompt_text(label, f"{description} ({choices_text})", default).lower()
        if value in choices:
            return value
        print(f"Please choose one of: {choices_text}")


def _print_title_alias_mode_guide() -> None:
    print("title_alias_mode options:")
    print("- off: only use your exact job title; shortest query, strictest recall.")
    print("- core: add a few common aliases; balanced recall and precision.")
    print("- broad: add more aliases; longest query, highest recall, more noise.")
    print("")


def _print_location_mode_guide() -> None:
    print("location_mode options:")
    print("- strict: only use your exact input location.")
    print("- expanded: use city + expanded location terms (recommended).")
    print("- country_only: use only country-level location term; widest recall.")
    print("")


def _collect_interactive(args: argparse.Namespace) -> argparse.Namespace:
    print("Interactive setup started. Press Enter to accept defaults for optional fields.")
    args.job_title = args.job_title or _prompt_text("job_title", "Target role to search")
    args.location = args.location or _prompt_text("location", "City or country to target")

    _print_title_alias_mode_guide()
    args.title_alias_mode = _prompt_choice(
        "title_alias_mode",
        "How many title aliases to use in query",
        ["off", "core", "broad"],
        args.title_alias_mode,
    )
    _print_location_mode_guide()
    args.location_mode = _prompt_choice(
        "location_mode",
        "How strict location filter should be",
        ["strict", "expanded", "country_only"],
        args.location_mode,
    )
    if args.location_mode == "expanded":
        args.location_expand_level = _prompt_int(
            "location_expand_level",
            "How far to expand mapped location terms (1=narrow, 2=balanced, 3=wide)",
            args.location_expand_level,
        )
        args.location_expand_level = max(1, min(3, args.location_expand_level))
    raw_search_args = _prompt_text(
        "search_args",
        "Keywords for search only, comma-separated. Added to shortest baseline query",
        ",".join(args.search_args),
    )
    args.search_args = _normalize_search_args([raw_search_args])

    args.pages_per_query = _prompt_int("pages_per_query", "How many Google result pages per query", args.pages_per_query)
    args.page_size = _prompt_int("page_size", "Expected Google results per page", args.page_size)
    print("Using default advanced settings from config.yaml:")
    print(
        f"delay_seconds={args.delay_seconds}, timeout_seconds={args.timeout_seconds}, "
        f"blocked_cooldown_seconds={args.blocked_cooldown_seconds}, jitter_ratio={args.jitter_ratio}"
    )
    print(
        "show_browser=%s, fail_fast=%s, raw_output_dir=%s, manual_antibot=%s, "
        "manual_antibot_timeout_seconds=%s, manual_antibot_poll_seconds=%s"
        % (
            args.show_browser,
            args.fail_fast,
            args.raw_output_dir,
            args.manual_antibot,
            args.manual_antibot_timeout_seconds,
            args.manual_antibot_poll_seconds,
        )
    )
    args.output = _prompt_text("output", "Final CSV output path", args.output)
    return args


def _should_prompt_interactive(args: argparse.Namespace) -> bool:
    # If --config flag is set, skip interactive mode entirely
    if args.config:
        return False
    required_missing = not args.job_title or not args.location
    return args.interactive or required_missing


def _setup_logging(debug_enabled: bool) -> Path:
    logs_dir = Path("outputs/logs")
    logs_dir.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    log_path = logs_dir / f"{timestamp}.log"

    root_logger = logging.getLogger()
    root_logger.setLevel(logging.DEBUG if debug_enabled else logging.INFO)
    root_logger.handlers.clear()

    formatter = logging.Formatter("%(asctime)s %(levelname)s %(name)s - %(message)s")
    console_handler = logging.StreamHandler()
    console_handler.setLevel(logging.DEBUG if debug_enabled else logging.INFO)
    console_handler.setFormatter(formatter)

    file_handler = logging.FileHandler(log_path, encoding="utf-8")
    file_handler.setLevel(logging.DEBUG)
    file_handler.setFormatter(formatter)

    root_logger.addHandler(console_handler)
    root_logger.addHandler(file_handler)
    return log_path


def main() -> None:
    args = parse_args()
    
    # Validate --config mode requirements
    if args.config:
        if not args.job_title or not args.location:
            print("Error: --config mode requires both 'job_title' and 'location' to be set in config.yaml")
            print(f"  job_title: {args.job_title or '(empty)'}")
            print(f"  location: {args.location or '(empty)'}")
            return
    
    if _should_prompt_interactive(args):
        args = _collect_interactive(args)

    log_path = _setup_logging(args.debug)
    logger.info("Stage[log] file=%s", log_path)
    if args.config:
        logger.info("Stage[cli] mode=config_file config_params_loaded=true")

    # Normalize search_args: break down comma-separated keywords into individual terms
    normalized_search_args = _normalize_search_args(args.search_args)

    search_input = SearchInput(
        job_title=args.job_title,
        location=args.location,
        search_args=normalized_search_args,
        title_alias_mode=args.title_alias_mode,
        location_mode=args.location_mode,
        location_expand_level=args.location_expand_level,
        pages_per_query=args.pages_per_query,
        page_size=args.page_size,
        delay_seconds=args.delay_seconds,
    )
    logger.info(
        (
            "Stage[cli] args job_title=%s location=%s search_args=%s "
            "title_alias_mode=%s location_mode=%s location_expand_level=%s output=%s mode=selenium"
        ),
        args.job_title,
        args.location,
        args.search_args,
        args.title_alias_mode,
        args.location_mode,
        args.location_expand_level,
        args.output,
    )

    client = SeleniumGoogleClient(
        timeout_seconds=args.timeout_seconds,
        jitter_ratio=args.jitter_ratio,
        blocked_cooldown_seconds=args.blocked_cooldown_seconds,
        headless=not args.show_browser,
        raw_output_dir=args.raw_output_dir,
        manual_antibot=args.manual_antibot,
        manual_antibot_timeout_seconds=args.manual_antibot_timeout_seconds,
        manual_antibot_poll_seconds=args.manual_antibot_poll_seconds,
    )

    logger.info("Stage[cli] pipeline_start")
    queries: list[str] = []
    try:
        if args.rescore_middle_csv:
            logger.info("Stage[cli] rescore_mode middle_csv=%s", args.rescore_middle_csv)
            candidates = run_rescore_from_middle(search_input, args.rescore_middle_csv)
        else:
            queries, candidates = run_pipeline(
                search_input,
                client=client,
                fail_fast=args.fail_fast,
                output_csv_path=args.output,
            )
    finally:
        client.close()
    logger.info("Stage[cli] pipeline_done queries=%s candidates=%s", len(queries), len(candidates))
    output_path = export_candidates_to_csv(candidates, args.output)
    logger.info("Stage[cli] run_complete output=%s", output_path)

    enabled_filter_dims = load_enabled_filter_dimensions()
    if enabled_filter_dims:
        filtered_candidates = _apply_strong_filter(candidates, enabled_filter_dims)
        filtered_output_path = export_candidates_to_csv(
            filtered_candidates,
            _derive_filter_output_path(args.output),
        )
        logger.info(
            "Stage[filter] enabled_dims=%s filtered_candidates=%s output=%s",
            enabled_filter_dims,
            len(filtered_candidates),
            filtered_output_path,
        )
    else:
        filtered_output_path = None
        logger.info("Stage[filter] disabled reason=no_true_filter_dims")

    if queries:
        print("Generated queries:")
        for index, query in enumerate(queries, start=1):
            print(f"{index}. {query}")
    print(f"Candidate count: {len(candidates)}")
    print(f"CSV exported to: {output_path}")
    if filtered_output_path:
        print(f"Filtered CSV exported to: {filtered_output_path}")
    print(f"Run log exported to: {log_path}")


if __name__ == "__main__":
    main()
