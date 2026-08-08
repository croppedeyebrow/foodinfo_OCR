"""Versioned SQL migration runner for the dedicated metadata schema."""

from __future__ import annotations

import hashlib
from dataclasses import dataclass
from pathlib import Path


class MigrationError(RuntimeError):
    pass


@dataclass(frozen=True, slots=True)
class Migration:
    version: str
    name: str
    path: Path
    checksum: str


def default_migrations_dir() -> Path:
    return Path(__file__).resolve().parent / "migrations"


def discover_migrations(migrations_dir: Path | None = None) -> list[Migration]:
    root = migrations_dir or default_migrations_dir()
    migrations: list[Migration] = []
    for path in sorted(root.glob("[0-9][0-9][0-9][0-9]_*.up.sql")):
        version = path.name.split("_", 1)[0]
        migrations.append(
            Migration(
                version=version,
                name=path.name,
                path=path,
                checksum=hashlib.sha256(path.read_bytes()).hexdigest(),
            )
        )
    return migrations


def apply_migrations(
    database_url: str,
    *,
    migrations_dir: Path | None = None,
) -> list[str]:
    import psycopg

    migrations = discover_migrations(migrations_dir)
    applied_now: list[str] = []
    with psycopg.connect(database_url) as connection:
        with connection.transaction():
            connection.execute("CREATE SCHEMA IF NOT EXISTS pipeline_metadata")
            connection.execute(
                """
                CREATE TABLE IF NOT EXISTS pipeline_metadata.schema_migrations (
                    version TEXT PRIMARY KEY,
                    name TEXT NOT NULL,
                    checksum TEXT NOT NULL,
                    applied_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP
                )
                """
            )
            connection.execute(
                "SELECT pg_advisory_xact_lock(hashtext(%s))",
                ("naenglog_pipeline_metadata_migrations",),
            )
            rows = connection.execute(
                "SELECT version, checksum FROM pipeline_metadata.schema_migrations"
            ).fetchall()
            applied = {str(row[0]): str(row[1]) for row in rows}

            for migration in migrations:
                previous = applied.get(migration.version)
                if previous is not None:
                    if previous != migration.checksum:
                        raise MigrationError(
                            f"migration checksum changed: {migration.name}"
                        )
                    continue
                connection.execute(migration.path.read_text(encoding="utf-8"))
                connection.execute(
                    """
                    INSERT INTO pipeline_metadata.schema_migrations
                        (version, name, checksum)
                    VALUES (%s, %s, %s)
                    """,
                    (migration.version, migration.name, migration.checksum),
                )
                applied_now.append(migration.version)
    return applied_now
