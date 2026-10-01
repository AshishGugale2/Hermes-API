"""Run the Liquibase CLI using the application's database configuration."""

import argparse
import getpass
import os
from pathlib import Path
import subprocess
import sys
from urllib.parse import parse_qsl, urlencode, urlsplit, unquote

from app.core.config import Settings

ROOT = Path(__file__).resolve().parents[1]
MIGRATIONS = ROOT / "migrations"
if not MIGRATIONS.is_dir():
    MIGRATIONS = Path(sys.prefix) / "share" / "hermes-api" / "migrations"


def liquibase_environment(database_url, schema="public"):
    parsed = urlsplit(database_url)
    if parsed.scheme not in {"postgresql", "postgres"} or not parsed.hostname:
        raise ValueError("Liquibase requires a PostgreSQL URL with a TCP hostname.")
    host = parsed.hostname
    if ":" in host:
        host = "[" + host + "]"
    database = parsed.path.lstrip("/")
    if not database:
        raise ValueError("DATABASE_URL must include a database name.")
    query = dict(parse_qsl(parsed.query))
    jdbc = f"jdbc:postgresql://{host}:{parsed.port or 5432}/{database}"
    if query:
        jdbc += "?" + urlencode(query)
    env = os.environ.copy()
    env.pop("LIQUIBASE_BINARY", None)
    env.update(
        {
            "LIQUIBASE_COMMAND_URL": jdbc,
            "LIQUIBASE_COMMAND_USERNAME": unquote(parsed.username or os.getenv("PGUSER") or getpass.getuser()),
            "LIQUIBASE_COMMAND_PASSWORD": unquote(parsed.password or os.getenv("PGPASSWORD", "")),
            "LIQUIBASE_COMMAND_DEFAULT_SCHEMA_NAME": schema,
            "LIQUIBASE_COMMAND_CHANGELOG_FILE": "db.changelog.xml",
            "LIQUIBASE_SEARCH_PATH": str(MIGRATIONS),
            "LIQUIBASE_ANALYTICS_ENABLED": "false",
        }
    )
    return env


def run(database_url, schema, command, *arguments):
    binary = os.getenv("LIQUIBASE_BINARY", "liquibase")
    return subprocess.run(
        [binary, command, *arguments],
        env=liquibase_environment(database_url, schema),
        cwd=MIGRATIONS,
        check=True,
    )


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=("validate", "status", "update", "update-sql", "rollback-count"))
    parser.add_argument("--count", type=int)
    args = parser.parse_args()
    settings = Settings.from_env()
    arguments = []
    if args.command == "rollback-count":
        if args.count is None or args.count < 1:
            parser.error("rollback-count requires a positive --count")
        arguments = ["--count", str(args.count)]
    try:
        run(settings.database_url, settings.database_schema, args.command, *arguments)
    except FileNotFoundError:
        parser.exit(1, "Liquibase is not installed. Install its CLI or use docker compose run --rm migrate.\n")


if __name__ == "__main__":
    main()
