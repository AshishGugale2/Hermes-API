# Hermes API

FastAPI service for IPO snapshots, mailing lists, subscription alerts, and SMTP
delivery. Requires Python 3.11+, PostgreSQL, and Liquibase 4.33.0 for migrations.

## Structure

```text
app/
  main.py                    Application factory and lifespan
  core/                      Validated settings, logging, dependency composition
  api/routes/                HTTP endpoints grouped by domain
  schemas/                   Pydantic request/response models
  db/database.py             PostgreSQL pool and transaction management
  db/repositories/           Snapshot, mailing-list, trigger, notification SQL
  services/                  IPO refresh, alert evaluation, SMTP, email rendering
  integrations/              Subscription source client and parsing
  jobs/                      Manual refresh and standalone scheduler
  templates/                 Packaged HTML email assets
migrations/
  db.changelog.xml           Ordered Liquibase changesets
  sql/                       Forward and rollback SQL
scripts/                     Liquibase runner and SQLite import
tests/                       API, services, repositories, migration integration
```

Routes access the application container through FastAPI dependencies. Services
coordinate business workflows; repositories own database queries. The API
creates its pool during startup and closes it during shutdown. Importing the app
does not connect to PostgreSQL. Startup verifies the required migrations and
fails clearly if they have not been applied.

The old `app.repository`, `app.models`, `app.scraper`, `app.mail_templates`,
`app.refresh`, and `app.scheduler` modules provide compatibility exports.
New application code should use the modules above.

## Local Development

Create a Python 3.11+ environment and install the project:

```sh
python3.12 -m venv .venv
. .venv/bin/activate
pip install -e '.[dev]'
```

Configure a local `.env` using the keys in `.env.example`. Set `DATABASE_URL`
to an existing PostgreSQL database, including its user and credentials.
`DATABASE_SCHEMA` defaults to `public`; a custom schema must already exist.
Keep `.env` out of Git. Shell environment variables override file values.

Install the Liquibase CLI and run migrations before starting either process:

```sh
python -m scripts.migrate validate
python -m scripts.migrate update
uvicorn app.main:app --reload --host 127.0.0.1 --port 8000
```

Run the scheduler separately:

```sh
python -m app.jobs.scheduler
```

It refreshes at 09:30, 11:30, 13:30, and 15:30 Asia/Kolkata on weekdays.
Run one manual refresh with `python -m app.jobs.refresh`. API and scheduler
must point to the same database and schema. Logs go to standard output.

## Containers

Set `POSTGRES_DB`, `POSTGRES_USER`, and `POSTGRES_PASSWORD` in `.env`.
Set `CONTAINER_DATABASE_URL` to the same credentials with hostname `db`.
URL-encode special characters in credentials used in connection URLs.
`DATABASE_URL` is used by local CLI commands; `CONTAINER_DATABASE_URL` is
used by API/scheduler containers.

```sh
docker compose up --build -d
docker compose logs -f api scheduler
```

Compose waits for PostgreSQL to become healthy, runs a one-shot Liquibase
migration, then starts the API and scheduler. PostgreSQL data lives in a named
volume. The application image runs as a non-root user. The API binds to
`127.0.0.1:8000` by default. The database is not published to the host.

For an existing database, deploy the application image and run Liquibase as a
release step using that database's JDBC URL and migration credentials. Run
one scheduler instance; API workers can scale separately. Configure TLS and
access control at the deployment gateway. Provision a runtime database role
with data-access permissions and a separate migration role with DDL permissions.

For later releases, run migrations explicitly before replacing services:

```sh
docker compose run --rm migrate update
docker compose up --build -d api scheduler
```

## Database Changes

Add a new SQL file and a new changeset in `migrations/db.changelog.xml`.
Include rollback SQL where practical. Never edit an already-applied changeset;
Liquibase tracks checksums. Review pending SQL before applying it:

```sh
python -m scripts.migrate status
python -m scripts.migrate update-sql
python -m scripts.migrate update
```

The initial changeset uses `CREATE TABLE IF NOT EXISTS` to adopt the schema
created by the earlier PostgreSQL implementation without deleting its rows.
This assumes that schema matches the earlier version; review differences first
if tables were changed manually.

Rollback requires a backup and review of the SQL. The initial rollback drops
all application tables and their data. To roll back only the latest changeset:

```sh
python -m scripts.migrate rollback-count --count 1
# Or: docker compose run --rm migrate rollback-count --count=1
```

The application verifies both current changesets at startup. A rollback may
require deploying the matching earlier application version.

## Importing SQLite Data

Stop writers, back up the SQLite file, apply Liquibase migrations to an empty
PostgreSQL database, then import:

```sh
python -m scripts.migrate update
python -m scripts.migrate_sqlite data/ipo_monitor.db
```

The importer preserves IDs, snapshots, mailing lists, triggers, notification
preferences, and alert history. It reads SQLite without modifying it and
refuses a populated PostgreSQL destination. An import error rolls back all
inserted rows. PostgreSQL enforces foreign keys, so invalid legacy references
must be corrected in the source before retrying. Review reported counts before
restarting services.

## Configuration

| Variable | Purpose |
| --- | --- |
| `DATABASE_URL` | PostgreSQL URL for local/application processes |
| `DATABASE_SCHEMA` | Existing schema, defaults to `public` |
| `DB_POOL_MAX` | Connections per process, defaults to 10, minimum 2 |
| `IPO_CACHE_MINUTES` | Snapshot freshness window, defaults to 15 |
| `CORS_ORIGINS` | Comma-separated browser origins |
| `LOG_LEVEL` | Standard Python logging level, defaults to INFO |
| `SMTP_HOST` | SMTP server; unset means log-only delivery |
| `SMTP_PORT` | SMTP port, defaults to 587 |
| `SMTP_USE_TLS` | Enable STARTTLS, defaults to true |
| `SMTP_USERNAME`, `SMTP_PASSWORD` | SMTP credentials |
| `SMTP_FROM` | Sender address |
| `LIQUIBASE_BINARY` | Optional path to the local Liquibase executable |

Matching alerts are grouped by mailing list and recorded once per trigger/IPO.
A PostgreSQL advisory lock coordinates simultaneous alert evaluations across
processes. Failed SMTP attempts remain retryable on the next refresh. Log-only
delivery is recorded as handled when no SMTP host is configured. SMTP delivery
and event storage are not an atomic operation; delivery followed by a process
failure before recording can still cause a repeated email.

## Endpoints

- `GET /api/health`: liveness
- `GET /api/health/ready`: database/schema readiness
- `GET /api/ipos`, `POST /api/ipos/refresh`
- `GET/POST /api/mailing-lists`, `PUT/DELETE /api/mailing-lists/{id}`
- `GET/POST /api/triggers`, `PUT/DELETE /api/triggers/{id}`
- `POST /api/triggers/{id}/toggle`, `GET /api/trigger-events`
- `GET /api/ipo-alerts`, `POST /api/ipo-alerts/pause`
- `POST /api/ipos/send-email`
- `GET /docs`: OpenAPI documentation

## Verification

Use a dedicated PostgreSQL test database. Tests create and remove isolated
schemas, and SMTP is disabled for repository integration tests.

```sh
export TEST_DATABASE_URL="postgresql://user:password@localhost:5432/hermes_test"
ruff check .
pytest -q
python -m build
docker compose --env-file .env.example config --quiet
```

Repository/API tests load the migration SQL as fixtures. Separate Liquibase
tests exercise validation, repeatable updates, rollback/reapply, and adoption
of an existing schema through the real CLI. Database tests skip without
`TEST_DATABASE_URL`; Liquibase tests also require the CLI.
GitHub Actions runs these checks with Python 3.12 and PostgreSQL 17 and builds
the deployment image.
