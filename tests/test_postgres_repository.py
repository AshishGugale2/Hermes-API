import unittest

import psycopg2
from fastapi.testclient import TestClient

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


if __name__ == "__main__":
    unittest.main()
