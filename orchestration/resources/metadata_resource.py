"""Dagster boundary around the normalizer metadata repository."""

from __future__ import annotations

from pathlib import Path

import dagster as dg

from orchestration.artifact import ArtifactReference


class PipelineMetadataResource(dg.ConfigurableResource):
    database_url: str
    data_root: str = "/data"
    contracts_dir: str = "/app/contracts"
    code_version: str = "dev"

    def register_collection_submission(
        self, *, batch_id: str, member: str
    ) -> ArtifactReference:
        from src.metadata.migrations import apply_migrations
        from src.metadata.repository import MetadataRepository
        from src.metadata.submission_adapter import register_accepted_submission

        apply_migrations(self.database_url)
        snapshot = register_accepted_submission(
            MetadataRepository(self.database_url),
            data_root=Path(self.data_root),
            batch_id=batch_id,
            member=member,
            code_version=self.code_version,
            contracts_dir=Path(self.contracts_dir),
        )
        artifact = next(
            item
            for item in snapshot["artifacts"]
            if item["logical_name"] == "collection_manifest"
        )
        return ArtifactReference(
            artifact_id=str(artifact["artifact_id"]),
            logical_name=str(artifact["logical_name"]),
            path=str(artifact["path"]),
            format=str(artifact["format"]),
            checksum=str(artifact["checksum"]),
            byte_size=int(artifact["byte_size"]),
            batch_id=batch_id,
            schema_version=artifact.get("schema_version"),
            row_count=artifact.get("row_count"),
            code_version=artifact.get("code_version"),
            rule_version=artifact.get("rule_version"),
        )
