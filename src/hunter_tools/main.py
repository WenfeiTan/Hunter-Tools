"""CLI entrypoint for Hunter Tools MVP."""

from __future__ import annotations

import argparse
import logging

from hunter_tools.exporter import export_candidates_to_csv
from hunter_tools.google_client import GoogleClient
from hunter_tools.models import SearchInput
from hunter_tools.pipeline import run_pipeline
from hunter_tools.selenium_client import SeleniumGoogleClient

logger = logging.getLogger(__name__)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Google X-Ray candidate sourcing MVP")
    parser.add_argument("--job-title", required=True, help="Job title, e.g., HRBP")
    parser.add_argument("--location", required=True, help="Location, e.g., Frankfurt")
    parser.add_argument("--yoe", required=True, type=int, help="Years of experience")
    parser.add_argument("--args", nargs="*", default=[], help="Custom keywords")
    parser.add_argument(
        "--title-alias-mode",
        choices=["off", "core", "broad"],
        default="core",
        help="Control job title alias expansion in query generation.",
    )
    parser.add_argument(
        "--location-mode",
        choices=["strict", "expanded", "country_only"],
        default="expanded",
        help="Control location strictness in query generation.",
    )
    parser.add_argument("--pages-per-query", type=int, default=2, help="Google pages per query")
    parser.add_argument("--page-size", type=int, default=10, help="Results per page")
    parser.add_argument("--delay-seconds", type=float, default=1.5, help="Request interval")
    parser.add_argument("--timeout-seconds", type=float, default=15.0, help="HTTP timeout per request")
    parser.add_argument("--max-retries", type=int, default=3, help="Max retries per Google request")
    parser.add_argument("--backoff-seconds", type=float, default=2.0, help="Base backoff in seconds")
    parser.add_argument(
        "--blocked-cooldown-seconds",
        type=float,
        default=25.0,
        help="Cooldown base seconds when anti-bot/rate-limit is detected",
    )
    parser.add_argument("--jitter-ratio", type=float, default=0.35, help="Random jitter ratio for delays")
    parser.add_argument("--fail-fast", action="store_true", help="Stop immediately when one query fails")
    parser.add_argument(
        "--acquisition-mode",
        choices=["selenium", "requests"],
        default="selenium",
        help="Acquisition engine. Default uses Selenium browser automation.",
    )
    parser.add_argument(
        "--show-browser",
        action="store_true",
        help="Show browser UI when using Selenium (default is headless).",
    )
    parser.add_argument(
        "--raw-output-dir",
        default="outputs/raw_pages",
        help="Directory to persist raw fetched HTML pages before parsing.",
    )
    parser.add_argument("--debug", action="store_true", help="Enable debug logging")
    parser.add_argument("--output", default="outputs/candidates.csv", help="CSV output path")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    logging.basicConfig(
        level=logging.DEBUG if args.debug else logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s - %(message)s",
    )

    search_input = SearchInput(
        job_title=args.job_title,
        location=args.location,
        yoe=args.yoe,
        args=args.args,
        title_alias_mode=args.title_alias_mode,
        location_mode=args.location_mode,
        pages_per_query=args.pages_per_query,
        page_size=args.page_size,
        delay_seconds=args.delay_seconds,
    )
    logger.info(
        "Stage[cli] args job_title=%s location=%s yoe=%s args=%s title_alias_mode=%s location_mode=%s output=%s mode=%s",
        args.job_title,
        args.location,
        args.yoe,
        args.args,
        args.title_alias_mode,
        args.location_mode,
        args.output,
        args.acquisition_mode,
    )

    if args.acquisition_mode == "selenium":
        client = SeleniumGoogleClient(
            timeout_seconds=args.timeout_seconds,
            jitter_ratio=args.jitter_ratio,
            blocked_cooldown_seconds=args.blocked_cooldown_seconds,
            headless=not args.show_browser,
            raw_output_dir=args.raw_output_dir,
        )
    else:
        client = GoogleClient(
            timeout_seconds=args.timeout_seconds,
            max_retries=args.max_retries,
            backoff_seconds=args.backoff_seconds,
            jitter_ratio=args.jitter_ratio,
            blocked_cooldown_seconds=args.blocked_cooldown_seconds,
            raw_output_dir=args.raw_output_dir,
        )

    logger.info("Stage[cli] pipeline_start")
    try:
        queries, candidates = run_pipeline(search_input, client=client, fail_fast=args.fail_fast)
    finally:
        close_client = getattr(client, "close", None)
        if callable(close_client):
            close_client()
    logger.info("Stage[cli] pipeline_done queries=%s candidates=%s", len(queries), len(candidates))
    output_path = export_candidates_to_csv(candidates, args.output)
    logger.info("Stage[cli] run_complete output=%s", output_path)

    print("Generated queries:")
    for index, query in enumerate(queries, start=1):
        print(f"{index}. {query}")
    print(f"Candidate count: {len(candidates)}")
    print(f"CSV exported to: {output_path}")


if __name__ == "__main__":
    main()
