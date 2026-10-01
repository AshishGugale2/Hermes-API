import sqlite3
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

import psycopg2
from fastapi.testclient import TestClient

from scripts.migrate_sqlite import migrate
from tests.postgres_helpers import postgres_repository


class PostgreSQLRepositoryTests(unittest.TestCase):
    def test_api_toggle_and_pause_use_postgres_booleans(self):
        with postgres_repository() as repo:
            from app.main import create_app

            with TestClient(create_app(container=repo.container)) as client:
                list_id = repo.create_mailing_list("Ops", "ops@example.com")
                trigger_id = repo.create_trigger("Ops", 5, ">", list_id)
                response = client.post(f"/api/triggers/{trigger_id}/toggle", json={"active": False})
                self.assertEqual(response.status_code, 200)
                self.assertFalse(repo.list_triggers()[0]["active"])
                self.assertEqual(client.post("/api/triggers/999/toggle", json={"active": False}).status_code, 404)
                response = client.post("/api/ipo-alerts/pause", json={"ipo_id": "ipo-1", "paused": True})
                self.assertEqual(response.status_code, 200)
                self.assertTrue(client.get("/api/ipo-alerts").json()[0]["paused"])
                client.post("/api/ipo-alerts/pause", json={"ipo_id": "ipo-1", "paused": False})
                self.assertFalse(repo.is_ipo_paused("ipo-1"))

    def test_rolls_back_failed_transaction(self):
        with postgres_repository() as repo:
            with self.assertRaises(psycopg2.errors.UniqueViolation):
                with repo._connect() as cursor:
                    cursor.execute(
                        "INSERT INTO mailing_lists (name, emails) VALUES (%s, %s)", ("Ops", "ops@example.com")
                    )
                    cursor.execute(
                        "INSERT INTO mailing_lists (name, emails) VALUES (%s, %s)", ("Ops", "ops@example.com")
                    )
            self.assertEqual(repo.list_mailing_lists(), [])

    def test_trigger_update_preserves_disabled_state_and_rejects_invalid_list(self):
        with postgres_repository() as repo:
            list_id = repo.create_mailing_list("Ops", "ops@example.com")
            trigger_id = repo.create_trigger("Ops", 5, ">", list_id, active=False)
            repo.update_trigger(trigger_id, threshold=8)
            self.assertEqual(repo.list_triggers(active_only=True), [])
            with self.assertRaises(ValueError):
                repo.update_trigger(trigger_id, threshold=9, mailing_list_id=999)
            self.assertEqual(repo.list_triggers()[0]["threshold"], 8)

    def test_import_preserves_ids_and_resets_identity(self):
        with postgres_repository() as repo, TemporaryDirectory() as directory:
            source_path = Path(directory) / "old.db"
            source = sqlite3.connect(source_path)
            try:
                with source:
                    source.execute(
                        "CREATE TABLE mailing_lists (id INTEGER PRIMARY KEY, name TEXT, emails TEXT, created_at TEXT)"
                    )
                    source.execute(
                        "INSERT INTO mailing_lists VALUES (42, 'Ops', 'ops@example.com', '2026-09-27T12:00:00+00:00')"
                    )
                    source.execute(
                        "CREATE TABLE mail_triggers (id INTEGER PRIMARY KEY, name TEXT, threshold REAL, operator TEXT, mailing_list_id INTEGER, active INTEGER)"
                    )
                    source.execute("INSERT INTO mail_triggers VALUES (27, 'Ops alert', 5, '>', 42, 0)")
            finally:
                source.close()
            counts = migrate(source_path, repo.container.database)
            self.assertEqual(counts["mailing_lists"], 1)
            self.assertEqual(repo.list_mailing_lists()[0]["id"], 42)
            self.assertFalse(repo.list_triggers()[0]["active"])
            self.assertGreater(repo.create_mailing_list("Investors", "investors@example.com"), 42)
            with self.assertRaises(ValueError):
                migrate(source_path, repo.container.database)

    def test_import_rolls_back_on_invalid_foreign_key(self):
        with postgres_repository() as repo, TemporaryDirectory() as directory:
            source_path = Path(directory) / "old.db"
            source = sqlite3.connect(source_path)
            try:
                with source:
                    source.execute("CREATE TABLE mailing_lists (id INTEGER PRIMARY KEY, name TEXT, emails TEXT)")
                    source.execute("INSERT INTO mailing_lists VALUES (1, 'Ops', 'ops@example.com')")
                    source.execute(
                        "CREATE TABLE mail_triggers (id INTEGER PRIMARY KEY, name TEXT, threshold REAL, operator TEXT, mailing_list_id INTEGER)"
                    )
                    source.execute("INSERT INTO mail_triggers VALUES (1, 'Invalid', 5, '>', 999)")
            finally:
                source.close()
            with self.assertRaises(psycopg2.errors.ForeignKeyViolation):
                migrate(source_path, repo.container.database)
            self.assertEqual(repo.list_mailing_lists(), [])


if __name__ == "__main__":
    unittest.main()
