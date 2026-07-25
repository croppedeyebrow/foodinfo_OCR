from __future__ import annotations

import os
from functools import lru_cache
from pathlib import Path


def _find_project_root() -> Path:
    """apps/console/src/config.py → project root."""
    here = Path(__file__).resolve()
    # src → console → apps → project
    return here.parents[3]


def _load_dotenv(project_root: Path) -> None:
    env_path = project_root / ".env"
    if not env_path.exists():
        return
    for line in env_path.read_text(encoding="utf-8").splitlines():
        text = line.strip()
        if not text or text.startswith("#") or "=" not in text:
            continue
        key, _, value = text.partition("=")
        key = key.strip()
        value = value.strip().strip('"').strip("'")
        if key and key not in os.environ:
            os.environ[key] = value


@lru_cache(maxsize=1)
def get_settings() -> "Settings":
    project_root = _find_project_root()
    _load_dotenv(project_root)
    return Settings(
        project_root=project_root,
        batch_member=os.getenv("BATCH_MEMBER", "unknown"),
        datasets_root=project_root / "datasets",
        outcome_root=project_root / "outcome",
    )


class Settings:
    def __init__(
        self,
        *,
        project_root: Path,
        batch_member: str,
        datasets_root: Path,
        outcome_root: Path,
    ) -> None:
        self.project_root = project_root
        self.batch_member = batch_member
        self.datasets_root = datasets_root
        self.outcome_root = outcome_root
        self.discovery_root = datasets_root / "discovery"

    def discovery_batch_dir(self, batch_id: str) -> Path:
        return self.discovery_root / batch_id

    def outcome_batch_dir(self, batch_id: str, member: str | None = None) -> Path:
        return self.outcome_root / (member or self.batch_member) / batch_id
