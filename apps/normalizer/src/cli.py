import os

import psycopg
import typer

app = typer.Typer(no_args_is_help=True)


@app.command()
def health() -> None:
    """PostgreSQL 연결을 확인한다."""
    database_url = os.environ["DATABASE_URL"]

    with psycopg.connect(database_url) as connection:
        with connection.cursor() as cursor:
            cursor.execute("SELECT current_database(), current_timestamp")
            database, current_time = cursor.fetchone()

    typer.echo("Normalizer container OK")
    typer.echo(f"Database: {database}")
    typer.echo(f"Database time: {current_time}")


if __name__ == "__main__":
    app()
