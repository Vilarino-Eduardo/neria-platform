"""Cria e restaura um backup local em banco temporário, sem alterar o banco principal."""

import json
import re
import subprocess
import uuid
from datetime import UTC, datetime
from pathlib import Path
from urllib.parse import urlparse

from sqlalchemy import create_engine, inspect, text
from sqlalchemy.engine import URL, make_url

from app.core.settings import get_settings

RESTORE_DATABASE_PATTERN = re.compile(r"^neria_restore_check_[0-9a-f]{12}$")
LOCAL_HOSTS = {"localhost", "127.0.0.1", "::1"}


def require_local_database(database_url: str) -> URL:
    parsed = urlparse(database_url.replace("postgresql+psycopg", "postgresql", 1))
    if parsed.hostname not in LOCAL_HOSTS:
        raise ValueError("A homologação aceita somente o PostgreSQL local.")
    return make_url(database_url)


def validate_restore_database(name: str) -> None:
    if not RESTORE_DATABASE_PATTERN.fullmatch(name):
        raise ValueError("Nome inseguro para o banco temporário de restauração.")


def docker_postgres(*arguments: str, stdout=None) -> None:
    subprocess.run(
        ["docker", "compose", "exec", "-T", "postgres", *arguments],
        check=True,
        stdout=stdout,
    )


def database_signature(database_url: URL) -> dict[str, object]:
    engine = create_engine(database_url)
    try:
        inspector = inspect(engine)
        tables = sorted(inspector.get_table_names(schema="public"))
        with engine.connect() as connection:
            counts = {
                table: connection.scalar(text(f'SELECT count(*) FROM "{table}"'))
                for table in tables
            }
            migration = connection.scalar(text("SELECT version_num FROM alembic_version"))
        return {"migration": migration, "tables": counts}
    finally:
        engine.dispose()


def main() -> int:
    try:
        source_url = require_local_database(get_settings().database_url)
    except ValueError as exc:
        print(json.dumps({"error": str(exc)}, ensure_ascii=False))
        return 2

    source_database = source_url.database or ""
    restore_database = f"neria_restore_check_{uuid.uuid4().hex[:12]}"
    validate_restore_database(restore_database)
    backup_directory = Path("backups")
    backup_directory.mkdir(exist_ok=True)
    timestamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
    backup_path = backup_directory / f"neria-local-{timestamp}.dump"
    restored_url = source_url.set(database=restore_database)

    try:
        with backup_path.open("wb") as backup_file:
            docker_postgres(
                "pg_dump",
                "-U",
                "neria",
                "-d",
                source_database,
                "--format=custom",
                "--no-owner",
                "--no-acl",
                stdout=backup_file,
            )
        if backup_path.stat().st_size == 0:
            raise RuntimeError("O arquivo de backup foi criado vazio.")

        docker_postgres("createdb", "-U", "neria", restore_database)
        with backup_path.open("rb") as backup_file:
            subprocess.run(
                [
                    "docker",
                    "compose",
                    "exec",
                    "-T",
                    "postgres",
                    "pg_restore",
                    "-U",
                    "neria",
                    "-d",
                    restore_database,
                    "--no-owner",
                    "--no-acl",
                ],
                check=True,
                stdin=backup_file,
            )

        source_signature = database_signature(source_url)
        restored_signature = database_signature(restored_url)
        signatures_match = source_signature == restored_signature
    except (OSError, subprocess.CalledProcessError, RuntimeError) as exc:
        print(json.dumps({"error": f"Falha na homologação: {exc}"}, ensure_ascii=False))
        return 1
    finally:
        try:
            docker_postgres(
                "dropdb", "-U", "neria", "--if-exists", "--force", restore_database
            )
        except subprocess.CalledProcessError:
            pass

    print(
        json.dumps(
            {
                "external_service_used": False,
                "source_database_modified": False,
                "backup": str(backup_path.resolve()),
                "backup_bytes": backup_path.stat().st_size,
                "migration": source_signature["migration"],
                "tables_verified": len(source_signature["tables"]),
                "all_row_counts_match": signatures_match,
                "temporary_database_removed": True,
            },
            ensure_ascii=False,
            indent=2,
        )
    )
    return 0 if signatures_match else 1


if __name__ == "__main__":
    raise SystemExit(main())
