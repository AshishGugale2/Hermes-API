import unittest
from datetime import datetime, timedelta

from tests.postgres_helpers import postgres_repository


class MailTriggerTests(unittest.TestCase):
    def test_process_snapshot_triggers_sends_once_per_ipo_per_rule(self):
        with postgres_repository() as repository:
            mailing_list_id = repository.create_mailing_list(
                "IPO Alerts",
                "ops@example.com, alerts@example.com",
            )
            trigger_id = repository.create_trigger(
                "overall_gt_10x",
                10.0,
                ">",
                mailing_list_id=mailing_list_id,
                active=True,
            )

            snapshot = {
                "fetched_at": "2026-09-27T12:00:00+00:00",
                "source_url": "https://example.com/ipo",
                "ipos": [
                    {
                        "id": "ipo-123",
                        "company": "IPO XYZ",
                        "overall_subscription": 12.4,
                        "closing_date": "2026-09-29",
                    }
                ],
            }

            first_run = repository.process_snapshot_triggers(snapshot)
            self.assertEqual(first_run["sent_count"], 1)
            self.assertEqual(len(repository.list_trigger_events(trigger_id)), 1)

            second_run = repository.process_snapshot_triggers(snapshot)
            self.assertEqual(second_run["sent_count"], 0)

            repository.pause_ipo_notifications("ipo-123", True, "already applied")
            third_run = repository.process_snapshot_triggers(snapshot)
            self.assertEqual(third_run["sent_count"], 0)

    def test_process_snapshot_triggers_groups_matches_by_rule_and_does_not_repeat_higher_priority_ipos(self):
        with postgres_repository() as repository:
            list_id = repository.create_mailing_list("IPO Alerts", "ops@example.com")
            trigger_10 = repository.create_trigger("overall_gt_10x", 10.0, ">", list_id, active=True)
            trigger_5 = repository.create_trigger("overall_gt_5x", 5.0, ">", list_id, active=True)

            snapshot = {
                "fetched_at": "2026-09-27T12:00:00+00:00",
                "source_url": "https://example.com/ipo",
                "ipos": [
                    {"id": "ipo-1", "company": "IPO One", "overall_subscription": 12.0, "closing_date": "2026-09-29"},
                    {"id": "ipo-2", "company": "IPO Two", "overall_subscription": 11.0, "closing_date": "2026-09-30"},
                    {"id": "ipo-3", "company": "IPO Three", "overall_subscription": 8.0, "closing_date": "2026-10-01"},
                ],
            }

            result = repository.process_snapshot_triggers(snapshot)

            self.assertEqual(result["sent_count"], 1)
            self.assertEqual(len(repository.list_trigger_events(trigger_10)), 2)
            self.assertEqual(len(repository.list_trigger_events(trigger_5)), 3)
            self.assertEqual(
                sorted(event["company"] for event in repository.list_trigger_events(trigger_5)),
                ["IPO One", "IPO Three", "IPO Two"],
            )
            self.assertEqual(
                sorted(event["status"] for event in repository.list_trigger_events(trigger_5)),
                ["covered_by_higher_trigger", "covered_by_higher_trigger", "sent"],
            )
            self.assertEqual(
                sorted(event["company"] for event in repository.list_trigger_events(trigger_10)),
                ["IPO One", "IPO Two"],
            )

    def test_process_snapshot_triggers_sends_separate_emails_per_mailing_list(self):
        with postgres_repository() as repository:
            ops_list_id = repository.create_mailing_list("Ops", "ops@example.com")
            investors_list_id = repository.create_mailing_list("Investors", "investors@example.com")
            ops_trigger = repository.create_trigger("overall_gt_8x", 8.0, ">", ops_list_id, active=True)
            investors_trigger = repository.create_trigger("overall_gt_5x", 5.0, ">", investors_list_id, active=True)

            snapshot = {
                "fetched_at": "2026-09-27T12:00:00+00:00",
                "source_url": "https://example.com/ipo",
                "ipos": [
                    {"id": "ipo-1", "company": "IPO One", "overall_subscription": 9.0, "closing_date": "2026-09-29"},
                    {"id": "ipo-2", "company": "IPO Two", "overall_subscription": 6.0, "closing_date": "2026-09-30"},
                ],
            }

            result = repository.process_snapshot_triggers(snapshot)

            self.assertEqual(result["sent_count"], 2)
            self.assertEqual(len(repository.list_trigger_events(ops_trigger)), 1)
            self.assertEqual(len(repository.list_trigger_events(investors_trigger)), 2)
            self.assertEqual(
                sorted(event["company"] for event in repository.list_trigger_events(investors_trigger)),
                ["IPO One", "IPO Two"],
            )
            self.assertEqual(repository.list_trigger_events(ops_trigger)[0]["company"], "IPO One")

    def test_create_trigger_rejects_missing_mailing_list(self):
        with postgres_repository() as repository:
            with self.assertRaises(ValueError):
                repository.create_trigger("missing list", 5.0, ">", 999, active=True)

    def test_lower_threshold_trigger_does_not_send_again_on_next_refresh(self):
        with postgres_repository() as repository:
            list_id = repository.create_mailing_list("Ops", "ops@example.com")
            t5 = repository.create_trigger("t5_5x", 5.0, ">", list_id, active=True)
            t1 = repository.create_trigger("t1_1x", 1.0, ">", list_id, active=True)
            snapshot = {
                "fetched_at": "2026-09-27T12:00:00+00:00",
                "source_url": "https://example.com/ipo",
                "ipos": [
                    {
                        "id": "ipo-42",
                        "company": "IPO Forty Two",
                        "overall_subscription": 6.0,
                        "closing_date": "2026-09-30",
                    },
                ],
            }

            first_run = repository.process_snapshot_triggers(snapshot)
            self.assertEqual(first_run["sent_count"], 1)
            self.assertEqual(len(repository.list_trigger_events(t5)), 1)
            self.assertEqual(len(repository.list_trigger_events(t1)), 1)
            self.assertEqual(repository.list_trigger_events(t1)[0]["status"], "covered_by_higher_trigger")

            second_run = repository.process_snapshot_triggers(snapshot)
            self.assertEqual(second_run["sent_count"], 0)
            self.assertEqual(len(repository.list_trigger_events(t5)), 1)
            self.assertEqual(len(repository.list_trigger_events(t1)), 1)

    def test_clear_orphaned_triggers_removes_missing_mailing_lists(self):
        with postgres_repository() as repository:
            list_id = repository.create_mailing_list("Ops", "ops@example.com")
            bad_trigger = repository.create_trigger("orphaned", 10.0, ">", list_id, active=True)

            with repository._connect() as connection:
                # Simulate legacy SQLite data where foreign keys were not enforced.
                connection.execute("ALTER TABLE mail_triggers DROP CONSTRAINT mail_triggers_mailing_list_id_fkey")
                connection.execute(
                    "UPDATE mail_triggers SET mailing_list_id = 999 WHERE id = %s",
                    (bad_trigger,),
                )

            repository.clear_orphaned_triggers()
            self.assertEqual(repository.list_triggers(), [])

    def test_manual_ipo_email_to_list_sends_for_selected_ipo(self):
        with postgres_repository() as repository:
            list_id = repository.create_mailing_list("Ops", "ops@example.com")

            result = repository.send_manual_ipo_email(
                ipo_id="ipo-999",
                company="IPO Demo",
                mailing_list_id=list_id,
                threshold=7.5,
                operator=">",
                closing_date="2026-09-29",
            )

            self.assertEqual(result["status"], "logged")
            self.assertEqual(result["recipients"], ["ops@example.com"])
            self.assertIn("IPO Demo", result["subject"])

    def test_build_mail_content_creates_professional_html_email(self):
        with postgres_repository() as repository:
            subject, body = repository._build_mail_content(
                "IPO Demo",
                {"operator": ">", "threshold": 7.5},
                "2026-09-29",
            )

            self.assertIn("IPO Demo", subject)
            self.assertIn("<html", body.lower())
            self.assertIn("IPO Alert", body)
            self.assertIn("Closing date", body)
            self.assertIn("7.50x", body)

    def test_mail_template_formats_today_and_human_readable_dates(self):
        with postgres_repository() as repository:
            today = datetime.today().date().isoformat()
            tomorrow = (datetime.today().date() + timedelta(days=1)).isoformat()

            _, today_body = repository._build_mail_content(
                "IPO Demo",
                {"operator": ">", "threshold": 7.5},
                today,
            )
            self.assertIn("Today", today_body)

            _, future_body = repository._build_mail_content(
                "IPO Demo",
                {"operator": ">", "threshold": 7.5},
                tomorrow,
            )
            self.assertRegex(future_body, r"\d{2} [A-Za-z]{3} \d{4}")
            self.assertNotIn("28092026", future_body)


if __name__ == "__main__":
    unittest.main()
