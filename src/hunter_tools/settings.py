"""Application settings via Dynaconf."""

from __future__ import annotations

from pathlib import Path

from dynaconf import Dynaconf


def load_settings() -> Dynaconf:
    project_root = Path(__file__).resolve().parents[2]
    settings_file = project_root / "config.yaml"
    return Dynaconf(
        settings_files=[str(settings_file)],
        environments=False,
        load_dotenv=False,
    )

