import os
from pathlib import Path
import shutil
import unittest
from uuid import uuid4

import psycopg2
from psycopg2 import sql

from scripts.migrate import liquibase_environment, run


class MigrationConfigurationTests(unittest.TestCase):
    def test_separates_encoded_credentials_from_jdbc_url(self):
        env = liquibase_environment("postgresql://ipo:p%40ss%2Fword@localhost:5432/ipo?sslmode=require")
        self.assertEqual(env["LIQUIBASE_COMMAND_PASSWORD"], "p@ss/word")
        self.assertEqual(env["LIQUIBASE_COMMAND_USERNAME"], "ipo")
        self.assertEqual(env["LIQUIBASE_COMMAND_URL"], "jdbc:postgresql://localhost:5432/ipo?sslmode=require")


class LiquibaseMigrationTests(unittest.TestCase):
    def setUp(self):
        self.url = os.getenv("TEST_DATABASE_URL")
        binary = os.getenv("LIQUIBASE_BINARY", "liquibase")
        if not self.url or not shutil.which(binary):
            self.skipTest("Set TEST_DATABASE_URL and install Liquibase to test migrations end to end.")
        self.schema = "migration_" + uuid4().hex
        self.connection = psycopg2.connect(self.url)
        self.connection.autocommit = True
        with self.connection.cursor() as cursor:
            cursor.execute(sql.SQL("CREATE SCHEMA {}").format(sql.Identifier(self.schema)))
            cursor.execute(sql.SQL("SET search_path TO {}").format(sql.Identifier(self.schema)))

    def tearDown(self):
        with self.connection.cursor() as cursor:
            cursor.execute(sql.SQL("DROP SCHEMA {} CASCADE").format(sql.Identifier(self.schema)))
        self.connection.close()

    def test_update_is_repeatable_and_rollback_reapply_works(self):
        run(self.url, self.schema, "validate")
        run(self.url, self.schema, "update")
        with self.connection.cursor() as cursor:
            cursor.execute("INSERT INTO mailing_lists (name, emails) VALUES ('Ops', 'ops@example.com')")
        run(self.url, self.schema, "update")
        with self.connection.cursor() as cursor:
            cursor.execute("SELECT COUNT(*) FROM databasechangelog")
            self.assertEqual(cursor.fetchone()[0], 2)
            cursor.execute("SELECT COUNT(*) FROM mailing_lists")
            self.assertEqual(cursor.fetchone()[0], 1)
        run(self.url, self.schema, "rollback-count", "--count", "1")
        with self.connection.cursor() as cursor:
            cursor.execute("SELECT to_regclass('idx_ipo_subscriptions_snapshot')")
            self.assertIsNone(cursor.fetchone()[0])
        run(self.url, self.schema, "update")
        with self.connection.cursor() as cursor:
            cursor.execute("SELECT to_regclass('idx_ipo_subscriptions_snapshot')")
            self.assertIsNotNone(cursor.fetchone()[0])

    def test_adopts_existing_schema_without_losing_data(self):
        initial = Path(__file__).resolve().parents[1] / "migrations/sql/001_initial_schema.sql"
        with self.connection.cursor() as cursor:
            cursor.execute(initial.read_text())
            cursor.execute("INSERT INTO mailing_lists (id, name, emails) VALUES (42, 'Ops', 'ops@example.com')")
        run(self.url, self.schema, "update")
        with self.connection.cursor() as cursor:
            cursor.execute("SELECT id FROM mailing_lists")
            self.assertEqual(cursor.fetchone()[0], 42)
        run(self.url, self.schema, "rollback-count", "--count", "2")
        with self.connection.cursor() as cursor:
            cursor.execute("SELECT to_regclass('snapshots')")
            self.assertIsNone(cursor.fetchone()[0])
