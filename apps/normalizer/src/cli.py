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

app = typer.Typer(no_args_is_help=True)


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


if __name__ == "__main__":
    app()
