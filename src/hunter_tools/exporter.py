"""CSV export utilities."""

from __future__ import annotations

import csv
import logging
from pathlib import Path

from hunter_tools.models import Candidate

logger = logging.getLogger(__name__)

CSV_COLUMNS = [
    "name",
    "score",
    "location_guess",
    "yoe_guess",
    "matched_keywords",
    "profile_url",
    "title",
    "snippet",
    "source_query",
    "timestamp",
]

MIDDLE_COLUMNS = [
    "name",
    "profile_url",
    "title",
    "snippet",
    "location_guess",
    "yoe_guess",
    "source_query",
    "timestamp",
]


def export_candidates_to_csv(candidates: list[Candidate], output_path: str) -> Path:
    path = Path(output_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    logger.info("Stage[export] writing csv path=%s rows=%s", path, len(candidates))
    with path.open("w", encoding="utf-8", newline="") as csv_file:
        writer = csv.DictWriter(csv_file, fieldnames=CSV_COLUMNS)
        writer.writeheader()
        for candidate in candidates:
            writer.writerow(candidate.to_row())
    logger.info("Stage[export] csv_done path=%s", path)
    return path


def export_middle_to_csv(rows: list[dict[str, str]], output_path: str) -> Path:
    path = Path(output_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    logger.info("Stage[middle] writing csv path=%s rows=%s", path, len(rows))
    with path.open("w", encoding="utf-8", newline="") as csv_file:
        writer = csv.DictWriter(csv_file, fieldnames=MIDDLE_COLUMNS)
        writer.writeheader()
        for row in rows:
            writer.writerow(row)
    logger.info("Stage[middle] csv_done path=%s", path)
    return path


def load_middle_from_csv(path: str) -> list[dict[str, str]]:
    file_path = Path(path)
    if not file_path.exists():
        raise FileNotFoundError(f"Middle CSV not found: {file_path}")
    with file_path.open("r", encoding="utf-8", newline="") as csv_file:
        reader = csv.DictReader(csv_file)
        rows = [dict(row) for row in reader]
    logger.info("Stage[middle] loaded path=%s rows=%s", file_path, len(rows))
    return rows
