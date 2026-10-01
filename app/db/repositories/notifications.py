import logging
from datetime import datetime, timezone
from typing import Any, Dict, Optional

from app.db.base import BaseRepository

logger = logging.getLogger(__name__)


class NotificationRepository(BaseRepository):
    def pause_ipo_notifications(self, ipo_id: str, paused: bool = True, reason: Optional[str] = None) -> Dict[str, Any]:
        normalized_ipo_id = str(ipo_id).strip()
        if not normalized_ipo_id:
            raise ValueError("An IPO id is required.")
        with self._connect() as connection:
            connection.execute(
                """
                INSERT INTO ipo_notifications (ipo_id, paused, paused_at, reason, updated_at)
                VALUES (%s, %s, %s, %s, %s)
                ON CONFLICT(ipo_id)
                DO UPDATE SET paused = excluded.paused,
                              paused_at = excluded.paused_at,
                              reason = excluded.reason,
                              updated_at = excluded.updated_at
                """,
                (
                    normalized_ipo_id,
                    bool(paused),
                    datetime.now(timezone.utc).isoformat() if paused else None,
                    reason,
                    datetime.now(timezone.utc).isoformat(),
                ),
            )
        return {"ipo_id": normalized_ipo_id, "paused": paused, "reason": reason}

    def is_ipo_paused(self, ipo_id: str) -> bool:
        with self._connect() as connection:
            row = connection.execute(
                "SELECT paused FROM ipo_notifications WHERE ipo_id = %s LIMIT 1",
                (str(ipo_id),),
            ).fetchone()
        return bool(row["paused"]) if row else False

    def list_notifications(self):
        with self._connect() as cursor:
            return [
                dict(row)
                for row in cursor.execute(
                    "SELECT ipo_id, paused, reason, paused_at, updated_at FROM ipo_notifications ORDER BY updated_at DESC"
                ).fetchall()
            ]
