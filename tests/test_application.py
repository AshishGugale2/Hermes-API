import unittest
from unittest.mock import patch

from fastapi.testclient import TestClient

from app.core.config import Settings
from app.core.container import Container
from app.main import create_app
from tests.postgres_helpers import postgres_repository


class ApplicationTests(unittest.TestCase):
    def test_create_app_does_not_open_database(self):
        settings = Settings(database_url="postgresql://unused/ipo")
        with patch("app.db.database.ThreadedConnectionPool") as pool:
            app = create_app(settings)
            self.assertTrue(app.routes)
            pool.assert_not_called()

    def test_startup_requires_migrations_and_closes_failed_pool(self):
        with postgres_repository() as repo:
            with repo._connect() as cursor:
                cursor.execute("DELETE FROM databasechangelog WHERE id = '002-query-indexes'")
            resources = Container(repo.container.settings)
            with self.assertRaisesRegex(RuntimeError, "migrations are pending"):
                with TestClient(create_app(container=resources)):
                    pass
            self.assertIsNone(resources.database._pool)

    def test_api_readiness_crud_and_refresh(self):
        with postgres_repository() as repo:
            with TestClient(create_app(container=repo.container)) as client:
                self.assertEqual(client.get("/api/health/ready").status_code, 200)
                first = client.post("/api/mailing-lists", json={"name": "First", "emails": "first@example.com"})
                second = client.post("/api/mailing-lists", json={"name": "Second", "emails": "second@example.com"})
                self.assertEqual(second.json()["emails"], ["second@example.com"])
                self.assertEqual(first.status_code, 200)
                self.assertEqual(
                    client.post(
                        "/api/mailing-lists", json={"name": "Second", "emails": "other@example.com"}
                    ).status_code,
                    409,
                )
                with patch(
                    "app.services.ipos.fetch_subscriptions",
                    return_value=[
                        {"id": "ipo-1", "company": "Example", "overall_subscription": 1.2, "closing_date": "2026-10-05"}
                    ],
                ):
                    response = client.post("/api/ipos/refresh")
                self.assertEqual(response.status_code, 200)
                self.assertFalse(response.json()["is_stale"])
                self.assertEqual(client.get("/api/ipos").json()["ipos"][0]["closing_date"], "2026-10-05")
            self.assertIsNone(repo.container.database._pool)

    def test_failed_email_can_retry_and_evaluations_are_serialized(self):
        with postgres_repository() as repo:
            list_id = repo.create_mailing_list("Ops", "ops@example.com")
            trigger_id = repo.create_trigger("Ops", 5, ">", list_id)
            snapshot = {"ipos": [{"id": "ipo-1", "company": "Example", "overall_subscription": 6}]}
            with repo.container.database.alert_lock() as acquired:
                self.assertTrue(acquired)
                self.assertEqual(repo.process_snapshot_triggers(snapshot)["sent_count"], 0)
            with patch.object(repo.container.email, "send", return_value={"status": "failed"}):
                self.assertEqual(repo.process_snapshot_triggers(snapshot)["sent_count"], 0)
            self.assertEqual(repo.list_trigger_events(trigger_id), [])
            self.assertEqual(repo.process_snapshot_triggers(snapshot)["sent_count"], 1)
