from __future__ import annotations

from typing import Literal

from .config import Settings, get_settings
from .summaries import infer_batch_member, validate_operator_batch_selection

ConsoleRole = Literal["COLLECTOR", "OPERATOR"]


def is_operator(settings: Settings | None = None) -> bool:
    current = settings or get_settings()
    return current.console_role == "OPERATOR"


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
