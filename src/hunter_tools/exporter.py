"""CSV export utilities."""

from __future__ import annotations

import csv
import logging
from pathlib import Path

from hunter_tools.config import CSV_COLUMNS
from hunter_tools.models import Candidate

logger = logging.getLogger(__name__)


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
