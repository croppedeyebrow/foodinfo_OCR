"""Filesystem resource that returns references, never full file payloads."""

from __future__ import annotations

import uuid
from pathlib import Path

import dagster as dg

from orchestration.artifact import ArtifactReference


class ArtifactStoreResource(dg.ConfigurableResource):
    data_root: str = "/data"
    contracts_dir: str = "/app/contracts"

    def accepted_batch_dir(self, batch_id: str) -> Path:
        return Path(self.data_root) / "inbox" / "accepted" / batch_id

    def accepted_batch_ids(self) -> list[str]:
        root = Path(self.data_root) / "inbox" / "accepted"
        if not root.is_dir():
            return []
        return sorted(
            path.name
            for path in root.iterdir()
            if path.is_dir() and (path / "manifest.json").is_file()
        )

    def accepted_member(self, batch_id: str) -> str:
        from src.contracts import load_json_file
        from src.submission import validate_batch_identity

        manifest_path = self.accepted_batch_dir(batch_id) / "manifest.json"
        payload = load_json_file(manifest_path)
        member = str(payload.get("member") or "")
        validate_batch_identity(batch_id, member)
        return member

    def collection_submission_reference(
        self, *, batch_id: str
    ) -> ArtifactReference:
        from src.contracts import load_json_file, validate_payload
        from src.submission import file_sha256, validate_batch_identity

        batch_dir = self.accepted_batch_dir(batch_id)
        manifest_path = batch_dir / "manifest.json"
        if not manifest_path.is_file():
            raise FileNotFoundError(f"accepted manifest not found: {manifest_path}")
        payload = load_json_file(manifest_path)
        member = str(payload.get("member") or "")
        validate_batch_identity(batch_id, member)
        result = validate_payload(
            "collection_submission",
            payload,
            contracts_dir=Path(self.contracts_dir),
            check_checksum=True,
        )
        if not result.ok:
            issues = "; ".join(
                f"{issue.error_code}:{issue.path}:{issue.message}"
                for issue in result.issues
            )
            raise ValueError(f"invalid collection submission: {issues}")
        if payload.get("status") != "ACCEPTED":
            raise ValueError("collection submission status must be ACCEPTED")

        checksum = file_sha256(manifest_path)
        artifact_id = str(
            uuid.uuid5(
                uuid.NAMESPACE_URL,
                f"collection_submission:{batch_id}:{checksum}",
            )
        )
        return ArtifactReference(
            artifact_id=artifact_id,
            logical_name="collection_manifest",
            path=manifest_path.as_posix(),
            format="JSON",
            checksum=checksum,
            byte_size=manifest_path.stat().st_size,
            batch_id=batch_id,
            schema_version=str(payload.get("schema_version") or "") or None,
            row_count=int(payload.get("row_count") or 0),
            code_version=str(payload.get("parser_version") or "") or None,
        )
