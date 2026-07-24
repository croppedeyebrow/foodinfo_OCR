from __future__ import annotations


def batch_belongs_to_member(batch_id: str, member: str) -> bool:
    """배치 ID(YYYYMMDD-팀원-일련번호)가 해당 팀원 소유인지 확인한다."""
    if not batch_id or not member:
        return False
    parts = [part for part in batch_id.split("-") if part]
    return member in parts
