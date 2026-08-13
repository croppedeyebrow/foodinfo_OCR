from __future__ import annotations

import os
from functools import lru_cache
from pathlib import Path


def _find_project_root() -> Path:
    """Prefer CONSOLE_PROJECT_ROOT (Docker). Else apps/console/src → project root."""
    override = os.getenv("CONSOLE_PROJECT_ROOT", "").strip()
    if override:
        return Path(override)
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


def _env_flag(name: str, *, default: bool = False) -> bool:
    raw = os.getenv(name)
    if raw is None:
        return default
    return raw.strip().lower() in {"1", "true", "yes", "on"}


def _team_members() -> tuple[str, ...]:
    raw = os.getenv("TEAM_MEMBERS", "jaeseong,sunyeong,woohee").strip()
    members = tuple(
        item.strip()
        for item in raw.split(",")
        if item.strip()
    )
    return members or ("jaeseong", "sunyeong", "woohee")


@lru_cache(maxsize=1)
def get_settings() -> "Settings":
    project_root = _find_project_root()
    _load_dotenv(project_root)
    datasets_root = Path(os.getenv("DATASETS_ROOT", str(project_root / "datasets")))
    outcome_root = Path(
        os.getenv("OUTCOME_HOST_ROOT", os.getenv("OUTCOME_ROOT_HOST", ""))
        or str(project_root / "outcome")
    )
    # Inside OCR containers OUTCOME_ROOT=/outcome; console on host/workspace uses ./outcome
    if outcome_root == Path("/outcome") and not outcome_root.exists():
        outcome_root = project_root / "outcome"
    return Settings(
        project_root=project_root,
        batch_member=os.getenv("BATCH_MEMBER", "unknown"),
        datasets_root=datasets_root,
        outcome_root=outcome_root,
        platform_mode=_env_flag("CONSOLE_PLATFORM_MODE"),
        team_members=_team_members(),
    )


class Settings:
    def __init__(
        self,
        *,
        project_root: Path,
        batch_member: str,
        datasets_root: Path,
        outcome_root: Path,
        platform_mode: bool,
        team_members: tuple[str, ...],
    ) -> None:
        self.project_root = project_root
        self.batch_member = batch_member
        self.datasets_root = datasets_root
        self.outcome_root = outcome_root
        self.platform_mode = platform_mode
        self.team_members = team_members
        self.discovery_root = datasets_root / "discovery"

    def discovery_batch_dir(self, batch_id: str) -> Path:
        return self.discovery_root / batch_id

    def outcome_batch_dir(self, batch_id: str, member: str | None = None) -> Path:
        return self.outcome_root / (member or self.batch_member) / batch_id
