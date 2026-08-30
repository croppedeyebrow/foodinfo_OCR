from __future__ import annotations

import re
from typing import Literal

from .config import Settings, get_settings
from .summaries import infer_batch_member, validate_operator_batch_selection

ConsoleRole = Literal["COLLECTOR", "OPERATOR"]

_DATASET_VERSION_PATTERN = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,127}$")


def is_operator(settings: Settings | None = None) -> bool:
    current = settings or get_settings()
    return current.console_role == "OPERATOR"


def validate_dataset_version(dataset_version: str) -> None:
    if not _DATASET_VERSION_PATTERN.match(dataset_version.strip()):
        raise ValueError(
            "dataset version은 영문·숫자로 시작하고 128자 이하여야 합니다. "
            "예: KFIA-2026-08"
        )


def resolve_operator_batch(
    batch_id: str, *, settings: Settings | None = None
) -> tuple[str, str]:
    current = settings or get_settings()
    member = infer_batch_member(batch_id, current.allowed_batch_members)
    if member is None:
        member = infer_batch_member(batch_id, current.team_members)
    if member is None:
        raise ValueError("배치 ID에서 팀원을 식별할 수 없습니다.")
    validate_operator_batch_selection(
        batch_id,
        member,
        current.allowed_batch_members,
    )
    return batch_id, member


def resolve_operator_dataset(
    dataset_version: str, *, settings: Settings | None = None
) -> tuple[str, str]:
    current = settings or get_settings()
    if not is_operator(current):
        raise ValueError("OPERATOR 권한이 필요합니다.")
    validate_dataset_version(dataset_version)
    member = current.console_operator.strip()
    if not member:
        raise ValueError("CONSOLE_OPERATOR가 설정되지 않았습니다.")
    return dataset_version.strip(), member
