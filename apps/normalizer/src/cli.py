from __future__ import annotations

import json
import os
from pathlib import Path

import typer

from .adapters.products_csv import adapt_products_csv, write_submission_json
from .contracts import (
    CONTRACT_SCHEMA_FILES,
    load_json_file,
    validate_payload,
)
from .storage_paths import ensure_storage_dirs
from .submission import (
    SubmissionError,
    submit_collection_batch,
    validate_and_write_report,
)

app = typer.Typer(no_args_is_help=True)


def _database_url() -> str:
    value = os.getenv("DATABASE_URL", "").strip()
    if not value:
        raise typer.BadParameter("DATABASE_URL 환경변수가 필요합니다.")
    return value


def _echo_json(payload: object) -> None:
    typer.echo(json.dumps(payload, ensure_ascii=False, indent=2, default=str))


@app.command()
def health() -> None:
    """PostgreSQL 연결을 확인한다."""
    import psycopg

    database_url = os.environ["DATABASE_URL"]

    with psycopg.connect(database_url) as connection:
        with connection.cursor() as cursor:
            cursor.execute("SELECT current_database(), current_timestamp")
            database, current_time = cursor.fetchone()

    typer.echo("Normalizer container OK")
    typer.echo(f"Database: {database}")
    typer.echo(f"Database time: {current_time}")


@app.command("list-contracts")
def list_contracts() -> None:
    """등록된 계약 이름을 출력한다."""
    for name in sorted(CONTRACT_SCHEMA_FILES):
        typer.echo(name)


@app.command("ensure-storage-dirs")
def ensure_storage_dirs_cmd(
    data_root: Path = typer.Option(Path("/data"), "--data-root"),
) -> None:
    """Bronze/inbox/silver/gold/quarantine 디렉터리를 생성한다 (기존 파일 삭제 없음)."""
    created = ensure_storage_dirs(data_root)
    for path in created:
        typer.echo(str(path))


@app.command("validate-contract")
def validate_contract(
    contract: str = typer.Option(..., "--contract", help="계약 이름"),
    file: Path = typer.Option(..., "--file", exists=True, readable=True),
    contracts_dir: Path | None = typer.Option(
        None, "--contracts-dir", help="schema 디렉터리 (기본: /app/contracts)"
    ),
    skip_checksum: bool = typer.Option(
        False, "--skip-checksum", help="content_hash 일치 검사 생략"
    ),
) -> None:
    """JSON 파일을 지정 계약으로 검증한다."""
    try:
        payload = load_json_file(file)
    except ValueError as error:
        typer.echo(str(error), err=True)
        raise typer.Exit(code=2) from error

    if contract not in CONTRACT_SCHEMA_FILES:
        typer.echo(
            f"UNKNOWN_CONTRACT: {contract}. Use list-contracts.",
            err=True,
        )
        raise typer.Exit(code=2)

    result = validate_payload(
        contract,
        payload,
        contracts_dir=contracts_dir,
        check_checksum=not skip_checksum,
    )
    if result.ok:
        typer.echo(f"OK: {contract} {file}")
        raise typer.Exit(code=0)

    for issue in result.issues:
        typer.echo(f"{issue.error_code}\t{issue.path}\t{issue.message}", err=True)
    raise typer.Exit(code=1)


@app.command("adapt-products-csv")
def adapt_products_csv_cmd(
    products: Path = typer.Option(..., "--products", exists=True, readable=True),
    batch_id: str = typer.Option(..., "--batch-id"),
    member: str = typer.Option(..., "--member"),
    output: Path = typer.Option(..., "--output"),
    failures: Path | None = typer.Option(None, "--failures", exists=True),
    discovery_dir: Path | None = typer.Option(None, "--discovery-dir", exists=True),
    status: str = typer.Option("DRAFT", "--status"),
    contracts_dir: Path | None = typer.Option(None, "--contracts-dir"),
) -> None:
    """기존 products.csv를 collection_submission JSON으로 변환한다 (원본 CSV 유지)."""
    payload = adapt_products_csv(
        products,
        batch_id=batch_id,
        member=member,
        status=status,
        failures_csv=failures,
        discovery_dir=discovery_dir,
    )
    write_submission_json(payload, output)

    result = validate_payload(
        "collection_submission",
        payload,
        contracts_dir=contracts_dir,
        check_checksum=True,
    )
    if not result.ok:
        for issue in result.issues:
            typer.echo(f"{issue.error_code}\t{issue.path}\t{issue.message}", err=True)
        raise typer.Exit(code=1)

    typer.echo(f"Wrote: {output}")
    typer.echo(f"row_count={payload['row_count']} content_hash={payload['content_hash']}")


@app.command("validate-collection")
def validate_collection_cmd(
    batch_id: str = typer.Option(..., "--batch-id"),
    member: str = typer.Option(..., "--member"),
    data_root: Path = typer.Option(Path("/data"), "--data-root"),
    outcome_root: Path = typer.Option(Path("/outcome"), "--outcome-root"),
    contracts_dir: Path | None = typer.Option(None, "--contracts-dir"),
) -> None:
    """Collection 배치를 검증하고 outcome에 validation_report.json을 기록한다."""
    try:
        report = validate_and_write_report(
            data_root=data_root,
            outcome_root=outcome_root,
            batch_id=batch_id,
            member=member,
            contracts_dir=contracts_dir,
        )
    except SubmissionError as error:
        typer.echo(f"{error.error_code}: {error}", err=True)
        raise typer.Exit(code=1) from error

    typer.echo(
        f"VALIDATION_{report.status}: batch_id={batch_id}, "
        f"products={report.counts['products']}, failures={report.counts['failures']}"
    )
    typer.echo(f"checksum={report.batch_sha256 or 'missing'}")
    if report.errors:
        for issue in report.errors:
            typer.echo(
                f"{issue['error_code']}\t{issue['path']}\t{issue['message']}",
                err=True,
            )
        raise typer.Exit(code=1)


@app.command("submit-collection")
def submit_collection_cmd(
    batch_id: str = typer.Option(..., "--batch-id"),
    member: str = typer.Option(..., "--member"),
    data_root: Path = typer.Option(Path("/data"), "--data-root"),
    outcome_root: Path = typer.Option(Path("/outcome"), "--outcome-root"),
    contracts_dir: Path | None = typer.Option(None, "--contracts-dir"),
) -> None:
    """검증된 Collection 배치를 accepted inbox로 원자적으로 제출한다."""
    try:
        report = submit_collection_batch(
            data_root=data_root,
            outcome_root=outcome_root,
            batch_id=batch_id,
            member=member,
            contracts_dir=contracts_dir,
        )
    except SubmissionError as error:
        typer.echo(f"{error.error_code}: {error}", err=True)
        raise typer.Exit(code=1) from error

    typer.echo(
        f"SUBMISSION_ACCEPTED: batch_id={batch_id}, "
        f"duplicate={str(report.duplicate).lower()}, "
        f"checksum={report.batch_sha256}"
    )


@app.command("seal-json")
def seal_json_cmd(
    file: Path = typer.Option(..., "--file", exists=True, readable=True),
    output: Path | None = typer.Option(None, "--output"),
) -> None:
    """JSON 객체에 canonical content_hash를 채워 저장한다."""
    from .contracts import seal_payload

    payload = load_json_file(file)
    sealed = seal_payload(payload)
    target = output or file
    target.write_text(
        json.dumps(sealed, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    typer.echo(f"Wrote: {target}")
    typer.echo(f"content_hash={sealed['content_hash']}")


@app.command("metadata-migrate")
def metadata_migrate() -> None:
    """pipeline_metadata schema의 미적용 migration을 실행한다."""
    from .metadata.migrations import apply_migrations

    applied = apply_migrations(_database_url())
    typer.echo(
        f"Metadata migrations applied: {', '.join(applied) if applied else 'none'}"
    )


@app.command("metadata-register-submission")
def metadata_register_submission(
    batch_id: str = typer.Option(..., "--batch-id"),
    member: str = typer.Option(..., "--member"),
    code_version: str = typer.Option(..., "--code-version"),
    data_root: Path = typer.Option(Path("/data"), "--data-root"),
    contracts_dir: Path | None = typer.Option(None, "--contracts-dir"),
) -> None:
    """accepted collection bundle을 metadata DB에 idempotent하게 등록한다."""
    from .metadata.migrations import apply_migrations
    from .metadata.repository import MetadataRepository
    from .metadata.submission_adapter import register_accepted_submission

    database_url = _database_url()
    apply_migrations(database_url)
    snapshot = register_accepted_submission(
        MetadataRepository(database_url),
        data_root=data_root,
        batch_id=batch_id,
        member=member,
        code_version=code_version,
        contracts_dir=contracts_dir,
    )
    _echo_json(snapshot)


@app.command("metadata-show-run")
def metadata_show_run(
    run_id: str = typer.Option(..., "--run-id"),
) -> None:
    """run과 step/artifact/quality metadata를 조회한다."""
    from .metadata.repository import MetadataRepository

    snapshot = MetadataRepository(_database_url()).get_run(run_id)
    if snapshot is None:
        typer.echo(f"RUN_NOT_FOUND: {run_id}", err=True)
        raise typer.Exit(code=1)
    _echo_json(snapshot)


@app.command("metadata-list-runs")
def metadata_list_runs(
    batch_id: str | None = typer.Option(None, "--batch-id"),
    limit: int = typer.Option(50, "--limit", min=1, max=1000),
) -> None:
    """최근 pipeline run을 조회한다."""
    from .metadata.repository import MetadataRepository

    rows = MetadataRepository(_database_url()).list_runs(
        batch_id=batch_id, limit=limit
    )
    _echo_json(rows)


@app.command("metadata-lineage")
def metadata_lineage(
    artifact_id: str = typer.Option(..., "--artifact-id"),
) -> None:
    """artifact의 상위 lineage를 조회한다."""
    from .metadata.repository import MetadataRepository

    rows = MetadataRepository(_database_url()).trace_ancestors(artifact_id)
    _echo_json(rows)


if __name__ == "__main__":
    app()
