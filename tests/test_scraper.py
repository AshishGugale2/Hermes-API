import unittest
from datetime import date

from app.scraper import _record_from_api_row, parse_subscriptions


class SubscriptionParserTests(unittest.TestCase):
    def test_parses_subscription_categories_from_semantic_headers(self):
        html = """
        <table>
          <tr><th>IPO Name</th><th>QIB</th><th>NII</th><th>Retail</th><th>Total</th></tr>
          <tr><td>Example Industries IPO</td><td>12.22x</td><td>6.5x</td><td>2.01x</td><td>5.27x</td></tr>
        </table>
        """

        records = parse_subscriptions(html)

        self.assertEqual(len(records), 1)
        self.assertEqual(records[0]["company"], "Example Industries IPO")
        self.assertEqual(records[0]["qib_subscription"], 12.22)
        self.assertEqual(records[0]["nii_subscription"], 6.5)
        self.assertEqual(records[0]["retail_subscription"], 2.01)
        self.assertEqual(records[0]["overall_subscription"], 5.27)

    def test_parses_the_live_api_row_shape(self):
        record = _record_from_api_row(
            {
                "~id": 2298,
                "Company": '<a href="/ipo/runwal-enterprises-ipo/2298/">Runwal Enterprises Ltd.</a> <span>O</span>',
                "~Issue_Close_Date": "2026-09-29",
                "QIB (x)": 1.01,
                "NII (x)": 0.29,
                "Retail (x)": 0.19,
                "Total (x)": 0.44,
            }
        )

        self.assertIsNotNone(record)
        assert record is not None
        self.assertEqual(record["id"], "2298")
        self.assertEqual(record["company"], "Runwal Enterprises Ltd.")
        self.assertEqual(record["close_date"], date(2026, 9, 29))

    def test_persists_closing_date_in_latest_snapshot(self):
        from tests.postgres_helpers import postgres_repository

        with postgres_repository() as repo:
            repo.save_snapshot(
                "https://example.com",
                [
                    {
                        "id": "ipo-1",
                        "company": "Example IPO",
                        "qib_subscription": 1.5,
                        "nii_subscription": 0.6,
                        "retail_subscription": 0.8,
                        "overall_subscription": 1.2,
                        "closing_date": "2026-09-29",
                    }
                ],
            )

            snapshot = repo.latest_snapshot()

            self.assertIsNotNone(snapshot)
            assert snapshot is not None
            self.assertEqual(snapshot["ipos"][0]["closing_date"], "2026-09-29")
