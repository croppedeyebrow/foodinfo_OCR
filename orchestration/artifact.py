"""Small serializable references passed between Dagster assets."""

from __future__ import annotations

from dataclasses import asdict, dataclass


@dataclass(frozen=True, slots=True)
class ArtifactReference:
    artifact_id: str
    logical_name: str
    path: str
    format: str
    checksum: str
    byte_size: int
    batch_id: str
    schema_version: str | None = None
    row_count: int | None = None
    code_version: str | None = None
    rule_version: str | None = None

    def materialization_metadata(self) -> dict[str, str | int]:
        return {
            key: value
            for key, value in asdict(self).items()
            if value is not None
        }
