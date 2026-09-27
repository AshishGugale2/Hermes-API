import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

from app.repository import SnapshotRepository


class MailAdminCrudTests(unittest.TestCase):
    def test_can_update_and_delete_mailing_lists_and_triggers(self):
        with TemporaryDirectory() as temp_dir:
            repo = SnapshotRepository(Path(temp_dir) / "ipo_monitor.db")
            list_id = repo.create_mailing_list("Ops", "ops@demo.com")
            trigger_id = repo.create_trigger("Ops alert", 5.0, ">", list_id)

            updated_list = repo.update_mailing_list(list_id, "Ops Team", "ops@demo.com, team@demo.com")
            self.assertEqual(updated_list["name"], "Ops Team")
            self.assertEqual(updated_list["emails"], ["ops@demo.com", "team@demo.com"])

            updated_trigger = repo.update_trigger(trigger_id, threshold=8.0, operator=">=", active=False)
            self.assertEqual(updated_trigger["threshold"], 8.0)
            self.assertFalse(updated_trigger["active"])

            repo.delete_trigger(trigger_id)
            self.assertEqual(repo.list_triggers(), [])

            repo.delete_mailing_list(list_id)
            self.assertEqual(repo.list_mailing_lists(), [])


if __name__ == "__main__":
    unittest.main()
