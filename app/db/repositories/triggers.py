import logging
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from app.db.base import BaseRepository

logger = logging.getLogger(__name__)


class TriggerRepository(BaseRepository):
    def __init__(self, database, mailing_lists):
        super().__init__(database)
        self.mailing_lists = mailing_lists

    def clear_orphaned_triggers(self) -> int:
        with self._connect() as connection:
            orphaned_rows = connection.execute(
                """
                SELECT t.id
                FROM mail_triggers t
                LEFT JOIN mailing_lists m ON m.id = t.mailing_list_id
                WHERE m.id IS NULL
                """
            ).fetchall()
            for row in orphaned_rows:
                connection.execute("DELETE FROM trigger_events WHERE trigger_id = %s", (row["id"],))
            cursor = connection.execute(
                """
                DELETE FROM mail_triggers
                WHERE id IN (
                    SELECT t.id
                    FROM mail_triggers t
                    LEFT JOIN mailing_lists m ON m.id = t.mailing_list_id
                    WHERE m.id IS NULL
                )
                """
            )
        logger.info("Cleared %d orphaned trigger(s) from the database", cursor.rowcount)
        return int(cursor.rowcount)

    def create_trigger(
        self,
        name: str,
        threshold: float,
        operator: str,
        mailing_list_id: int,
        active: bool = True,
        description: Optional[str] = None,
    ) -> int:
        cleaned_name = (name or "").strip()
        if not cleaned_name:
            raise ValueError("A trigger name is required.")
        if operator not in {">", ">=", "<", "<=", "=", "=="}:
            raise ValueError("Unsupported trigger operator.")
        self.mailing_lists.require_exists(int(mailing_list_id))
        with self._connect() as connection:
            cursor = connection.execute(
                """
                INSERT INTO mail_triggers (name, threshold, operator, mailing_list_id, active, description)
                VALUES (%s, %s, %s, %s, %s, %s) RETURNING id
                """,
                (cleaned_name, float(threshold), operator, int(mailing_list_id), bool(active), description),
            )
            new_id = int(cursor.fetchone()["id"])
        logger.info("Created trigger %s for mailing list %s", cleaned_name, mailing_list_id)
        return new_id

    def update_trigger(
        self,
        trigger_id: int,
        name: Optional[str] = None,
        threshold: Optional[float] = None,
        operator: Optional[str] = None,
        mailing_list_id: Optional[int] = None,
        active: Optional[bool] = None,
        description: Optional[str] = None,
    ) -> Dict[str, Any]:
        with self._connect() as connection:
            row = connection.execute(
                "SELECT id, name, threshold, operator, mailing_list_id, active, description, created_at FROM mail_triggers WHERE id = %s",
                (int(trigger_id),),
            ).fetchone()
        if row is None:
            raise ValueError("Trigger not found.")

        updated_name = (name or row["name"]).strip()
        if not updated_name:
            raise ValueError("A trigger name is required.")
        updated_operator = operator or row["operator"]
        if updated_operator not in {">", ">=", "<", "<=", "=", "=="}:
            raise ValueError("Unsupported trigger operator.")

        target_list_id = int(mailing_list_id) if mailing_list_id is not None else int(row["mailing_list_id"])
        self.mailing_lists.require_exists(target_list_id)
        with self._connect() as connection:
            connection.execute(
                """
                UPDATE mail_triggers
                SET name = %s, threshold = %s, operator = %s, mailing_list_id = %s, active = %s, description = %s
                WHERE id = %s
                """,
                (
                    updated_name,
                    float(threshold) if threshold is not None else float(row["threshold"]),
                    updated_operator,
                    int(mailing_list_id) if mailing_list_id is not None else int(row["mailing_list_id"]),
                    bool(row["active"]) if active is None else bool(active),
                    description if description is not None else row["description"],
                    int(trigger_id),
                ),
            )
        active_value = row["active"] if active is None else bool(active)
        return {
            "id": int(trigger_id),
            "name": updated_name,
            "threshold": float(threshold) if threshold is not None else float(row["threshold"]),
            "operator": updated_operator,
            "mailing_list_id": target_list_id,
            "active": bool(active_value),
            "description": description if description is not None else row["description"],
            "created_at": row["created_at"],
        }

    def delete_trigger(self, trigger_id: int) -> bool:
        with self._connect() as connection:
            cursor = connection.execute("DELETE FROM trigger_events WHERE trigger_id = %s", (int(trigger_id),))
            cursor = connection.execute("DELETE FROM mail_triggers WHERE id = %s", (int(trigger_id),))
        return cursor.rowcount > 0

    def list_triggers(self, active_only: bool = False) -> List[Dict[str, Any]]:
        base_query = """
            SELECT t.id, t.name, t.threshold, t.operator, t.mailing_list_id, t.active,
                   t.description, t.created_at, m.name AS mailing_list_name
            FROM mail_triggers t
            LEFT JOIN mailing_lists m ON m.id = t.mailing_list_id
        """
        params: List[Any] = []
        if active_only:
            base_query += " WHERE t.active = TRUE"
        base_query += " ORDER BY t.created_at DESC"
        with self._connect() as connection:
            rows = connection.execute(base_query, params).fetchall()
        return [
            {
                "id": row["id"],
                "name": row["name"],
                "threshold": row["threshold"],
                "operator": row["operator"],
                "mailing_list_id": row["mailing_list_id"],
                "mailing_list_name": row["mailing_list_name"],
                "active": bool(row["active"]),
                "description": row["description"],
                "created_at": row["created_at"],
            }
            for row in rows
        ]

    def list_trigger_events(self, trigger_id: Optional[int] = None) -> List[Dict[str, Any]]:
        query = """
            SELECT id, trigger_id, ipo_id, company, trigger_threshold, operator, closing_date,
                   sent_at, status, subject, body, message
            FROM trigger_events
        """
        params: List[Any] = []
        if trigger_id is not None:
            query += " WHERE trigger_id = %s"
            params.append(trigger_id)
        query += " ORDER BY sent_at DESC"
        with self._connect() as connection:
            rows = connection.execute(query, params).fetchall()
        return [
            {
                "id": row["id"],
                "trigger_id": row["trigger_id"],
                "ipo_id": row["ipo_id"],
                "company": row["company"],
                "trigger_threshold": row["trigger_threshold"],
                "operator": row["operator"],
                "closing_date": row["closing_date"],
                "sent_at": row["sent_at"],
                "status": row["status"],
                "subject": row["subject"],
                "body": row["body"],
                "message": row["message"],
            }
            for row in rows
        ]

    def event_exists(self, trigger_id: int, ipo_id: str) -> bool:
        with self._connect() as connection:
            row = connection.execute(
                "SELECT 1 FROM trigger_events WHERE trigger_id = %s AND ipo_id = %s LIMIT 1",
                (trigger_id, ipo_id),
            ).fetchone()
        return row is not None

    def toggle(self, trigger_id: int, active: bool) -> bool:
        with self._connect() as cursor:
            cursor.execute("UPDATE mail_triggers SET active = %s WHERE id = %s", (active, trigger_id))
            return cursor.rowcount > 0

    def record_events(self, events, subject, body, message):
        with self._connect() as cursor:
            cursor.executemany(
                """INSERT INTO trigger_events (
                    trigger_id, ipo_id, company, trigger_threshold, operator,
                    closing_date, sent_at, status, subject, body, message
                ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)""",
                [
                    (
                        event["trigger_id"],
                        event["ipo_id"],
                        event["company"],
                        event["trigger_threshold"],
                        event["operator"],
                        event["closing_date"],
                        datetime.now(timezone.utc).isoformat(),
                        event["status"],
                        subject,
                        body,
                        message,
                    )
                    for event in events
                ],
            )
