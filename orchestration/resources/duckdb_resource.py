"""DuckDB connection factory; transformation rules stay in application code."""

from __future__ import annotations

from contextlib import contextmanager
from pathlib import Path
from typing import Iterator

import dagster as dg


class DuckDBResource(dg.ConfigurableResource):
    database_path: str = "/data/pipeline.duckdb"

    @contextmanager
    def connect(self, *, read_only: bool = False) -> Iterator[object]:
        import duckdb

        path = Path(self.database_path)
        path.parent.mkdir(parents=True, exist_ok=True)
        connection = duckdb.connect(str(path), read_only=read_only)
        try:
            yield connection
        finally:
            connection.close()
