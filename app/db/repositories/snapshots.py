import logging
from datetime import datetime, timezone
from typing import Dict, List, Optional

from app.db.base import BaseRepository

logger = logging.getLogger(__name__)


class SnapshotStore(BaseRepository):
    def save_snapshot(self, source_url: str, ipos: List[Dict[str, object]]) -> Dict[str, object]:
        sorted_ipos = sorted(
            ipos,
            key=lambda ipo: (
                -(
                    float(ipo.get("overall_subscription"))
                    if ipo.get("overall_subscription") is not None
                    else float("-inf")
                ),
                str(ipo.get("company") or ""),
            ),
        )
        logger.info(sorted_ipos[0] if sorted_ipos else "No IPOs available")
        fetched_at = datetime.now(timezone.utc).isoformat()
        logger.info("Saving IPO snapshot for %s with %d records", source_url, len(sorted_ipos))
        with self._connect() as connection:
            cursor = connection.execute(
                "INSERT INTO snapshots (fetched_at, source_url, item_count) VALUES (%s, %s, %s) RETURNING id",
                (fetched_at, source_url, len(sorted_ipos)),
            )
            snapshot_id = cursor.fetchone()["id"]
            connection.executemany(
                """
                INSERT INTO ipo_subscriptions (
                    snapshot_id, ipo_id, company, qib_subscription, nii_subscription,
                    retail_subscription, overall_subscription, closing_date
                ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
                """,
                [
                    (
                        snapshot_id,
                        ipo["id"],
                        ipo["company"],
                        ipo.get("qib_subscription"),
                        ipo.get("nii_subscription"),
                        ipo.get("retail_subscription"),
                        ipo.get("overall_subscription"),
                        ipo.get("closing_date", ipo.get("close_date")),
                    )
                    for ipo in sorted_ipos
                ],
            )
        logger.info("IPO snapshot saved successfully at %s", fetched_at)
        snapshot = {"fetched_at": fetched_at, "source_url": source_url, "ipos": sorted_ipos}
        return snapshot

    def latest_snapshot(self) -> Optional[Dict[str, object]]:
        logger.debug("Fetching latest snapshot from database")
        with self._connect() as connection:
            snapshot = connection.execute(
                "SELECT id, fetched_at, source_url FROM snapshots ORDER BY id DESC LIMIT 1"
            ).fetchone()
            if snapshot is None:
                logger.info("No snapshot available in database yet")
                return None
            rows = connection.execute(
                """
                SELECT ipo_id, company, qib_subscription, nii_subscription,
                       retail_subscription, overall_subscription, closing_date
                FROM ipo_subscriptions
                WHERE snapshot_id = %s
                ORDER BY overall_subscription DESC NULLS LAST, company ASC
                """,
                (snapshot["id"],),
            ).fetchall()

        result = {
            "fetched_at": snapshot["fetched_at"],
            "source_url": snapshot["source_url"],
            "ipos": [
                {
                    "id": row["ipo_id"],
                    "company": row["company"],
                    "qib_subscription": row["qib_subscription"],
                    "nii_subscription": row["nii_subscription"],
                    "retail_subscription": row["retail_subscription"],
                    "overall_subscription": row["overall_subscription"],
                    "closing_date": row["closing_date"].isoformat()
                    if hasattr(row["closing_date"], "isoformat")
                    else row["closing_date"],
                }
                for row in rows
            ],
        }
        logger.debug("Loaded latest snapshot with %d IPOs", len(result["ipos"]))
        return result
