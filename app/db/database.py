from contextlib import contextmanager
from threading import BoundedSemaphore

from psycopg2 import OperationalError, sql
from psycopg2.extras import RealDictCursor
from psycopg2.pool import ThreadedConnectionPool


class RepositoryCursor(RealDictCursor):
    def execute(self, query, vars=None):
        super().execute(query, vars)
        return self


class Database:
    def __init__(self, settings):
        self.settings = settings
        self._pool = None
        self._slots = BoundedSemaphore(settings.db_pool_max)

    def open(self):
        if self._pool is None:
            self._pool = ThreadedConnectionPool(
                1,
                self.settings.db_pool_max,
                self.settings.database_url,
                connect_timeout=10,
                options="-c statement_timeout=30000 -c timezone=UTC",
            )

    def close(self):
        if self._pool is not None:
            self._pool.closeall()
            self._pool = None

    @contextmanager
    def cursor(self):
        if self._pool is None:
            raise RuntimeError("Database pool is not open.")
        if not self._slots.acquire(timeout=10):
            raise OperationalError("Database connection pool is busy.")
        try:
            connection = self._pool.getconn()
            try:
                with connection:
                    with connection.cursor(cursor_factory=RepositoryCursor) as cursor:
                        cursor.execute(
                            sql.SQL("SET LOCAL search_path TO {}").format(sql.Identifier(self.settings.database_schema))
                        )
                        yield cursor
            finally:
                self._pool.putconn(connection, close=bool(connection.closed))
        finally:
            self._slots.release()

    def check_ready(self):
        with self.cursor() as cursor:
            cursor.execute(
                """SELECT 1 FROM snapshots, ipo_subscriptions, mailing_lists,
                   mail_triggers, trigger_events, ipo_notifications LIMIT 0"""
            )
            row = cursor.execute(
                "SELECT COUNT(*) AS count FROM databasechangelog WHERE id IN ('001-initial-schema', '002-query-indexes')"
            ).fetchone()
            if row["count"] != 2:
                raise RuntimeError("Database migrations are pending; run Liquibase update.")

    @contextmanager
    def alert_lock(self):
        with self.cursor() as cursor:
            row = cursor.execute(
                "SELECT pg_try_advisory_xact_lock(hashtext(current_schema()), 48101) AS acquired"
            ).fetchone()
            yield row["acquired"]
