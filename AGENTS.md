# NaengLog Data Platform Agent Rules

## Source of truth

Before changing data-platform code, read in order:

1. `dev_order/README.md`
2. `dev_order/data_platform/00_execution_rules.md`
3. The one stage marked `READY` or `IN_PROGRESS`
4. Reference documents under `dev_docs/data_platform`
5. Existing contracts and tests for the affected producer and consumer

## Architecture constraints

- Python 3.12 is the primary implementation language.
- Use Polars expressions and Parquet for structured batch transformations.
- Dagster orchestrates existing application entrypoints; business rules do not live in Dagster definitions.
- Rust is optional and may only be introduced through `dev_order/data_platform/09_rust_benchmark_gate.md`.
- Do not introduce Go, Spark, Kafka, Airflow, or Kubernetes without a new approved ADR.
- Preserve `apps/console`, `apps/crawler`, `apps/ocr-parser`, and their existing CLI behavior.
- Team members use only collection and OCR features in Console.
- Do not expose reconciliation, quality approval, Gold publishing, pipeline DB, or Backend credentials in the team Console.

## Data safety

- Do not delete or rewrite existing files under `datasets` or `outcome` unless the active stage explicitly authorizes a migration.
- Raw crawl, image, OCR, and PDF artifacts are immutable inputs.
- Invalid records go to rejection or quarantine artifacts; never silently drop them.
- Backend receives only versioned Gold contract fields, not raw OCR/PDF payloads.
- Every published artifact requires schema version, checksum, row count, code/rule version, and source lineage.

## Change discipline

- Implement one numbered stage at a time.
- Present the intended files and compatibility impact before editing.
- Preserve unrelated user changes and avoid broad refactors.
- Do not invent domain thresholds, matching priorities, or confidence rules.
- Do not add custom Rust until a benchmark proves the need.
- Never use live Kurly, production databases, or destructive volume commands for routine tests.

## Required verification

- Contract tests for producer and consumer
- Unit tests for pure transformation/rule code
- Integration tests with local fixture data
- Existing crawler/OCR non-integration tests
- Format, lint, and type checks configured by the repository
- A completion report following `dev_order/data_platform/00_execution_rules.md`

## Archive rule

- `dev_docs/archive` and `dev_order/archive` are historical evidence only.
- Never execute an archived prompt as a current instruction.
