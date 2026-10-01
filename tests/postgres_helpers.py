import os
import unittest
from pathlib import Path
from xml.etree import ElementTree
from contextlib import contextmanager
from unittest.mock import patch
from uuid import uuid4

import psycopg2
from psycopg2 import sql

from app.repository import SnapshotRepository


@contextmanager
def postgres_repository():
    database_url = os.getenv("TEST_DATABASE_URL")
    if not database_url:
        raise unittest.SkipTest("Set TEST_DATABASE_URL to run PostgreSQL integration tests.")
    schema = "test_" + uuid4().hex
    connection = psycopg2.connect(database_url)
    connection.autocommit = True
    try:
        with connection.cursor() as cursor:
            cursor.execute(sql.SQL("CREATE SCHEMA {}").format(sql.Identifier(schema)))
        # Repository tests use the same SQL files as Liquibase in an isolated schema.
        migrations = Path(__file__).resolve().parents[1] / "migrations"
        changelog = ElementTree.parse(migrations / "db.changelog.xml")
        namespace = {"lb": "http://www.liquibase.org/xml/ns/dbchangelog"}
        with connection.cursor() as cursor:
            cursor.execute(sql.SQL("SET search_path TO {}").format(sql.Identifier(schema)))
            cursor.execute("CREATE TABLE databasechangelog (id TEXT)")
            for changeset in changelog.findall("lb:changeSet", namespace):
                file = changeset.find("lb:sqlFile", namespace)
                cursor.execute((migrations / file.attrib["path"]).read_text())
                cursor.execute("INSERT INTO databasechangelog (id) VALUES (%s)", (changeset.attrib["id"],))
        with patch.dict(os.environ, {"SMTP_HOST": ""}):
            repo = SnapshotRepository(database_url, schema=schema)
            try:
                yield repo
            finally:
                repo.close()
    finally:
        with connection.cursor() as cursor:
            cursor.execute(sql.SQL("DROP SCHEMA IF EXISTS {} CASCADE").format(sql.Identifier(schema)))
        connection.close()
