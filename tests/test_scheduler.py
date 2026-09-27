import unittest

from app.scheduler import TIMEZONE, create_scheduler


class SchedulerTests(unittest.TestCase):
    def test_registers_the_expected_weekday_schedule(self):
        scheduler = create_scheduler()
        job = scheduler.get_job("ipo-subscription-refresh")

        self.assertEqual(str(TIMEZONE), "Asia/Kolkata")
        self.assertIsNotNone(job)
        assert job is not None
        self.assertIn("day_of_week='mon-fri'", str(job.trigger))
        self.assertIn("hour='9,11,13,15'", str(job.trigger))
        self.assertIn("minute='30'", str(job.trigger))
