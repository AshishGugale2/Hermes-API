import logging
import re
from typing import Any, Dict, List, Optional

from app.db.base import BaseRepository

logger = logging.getLogger(__name__)


class MailingListRepository(BaseRepository):
    def create_mailing_list(self, name: str, emails: str) -> int:
        cleaned_name = (name or "").strip()
        if not cleaned_name:
            raise ValueError("A mailing list name is required.")
        recipient_list = self._parse_emails(emails)
        if not recipient_list:
            raise ValueError("Add at least one recipient email address.")
        with self._connect() as connection:
            cursor = connection.execute(
                "INSERT INTO mailing_lists (name, emails) VALUES (%s, %s) RETURNING id",
                (cleaned_name, ", ".join(recipient_list)),
            )
            new_id = int(cursor.fetchone()["id"])
        logger.info("Created mailing list %s with %d recipients", cleaned_name, len(recipient_list))
        return new_id

    def update_mailing_list(
        self, mailing_list_id: int, name: Optional[str] = None, emails: Optional[str] = None
    ) -> Dict[str, Any]:
        with self._connect() as connection:
            row = connection.execute(
                "SELECT id, name, emails, created_at FROM mailing_lists WHERE id = %s",
                (int(mailing_list_id),),
            ).fetchone()
        if row is None:
            raise ValueError("Mailing list not found.")

        updated_name = (name or row["name"]).strip()
        if not updated_name:
            raise ValueError("A mailing list name is required.")

        recipient_list = self._parse_emails(emails if emails is not None else row["emails"])
        if not recipient_list:
            raise ValueError("Add at least one recipient email address.")

        with self._connect() as connection:
            connection.execute(
                "UPDATE mailing_lists SET name = %s, emails = %s WHERE id = %s",
                (updated_name, ", ".join(recipient_list), int(mailing_list_id)),
            )

        return {
            "id": int(mailing_list_id),
            "name": updated_name,
            "emails": recipient_list,
            "created_at": row["created_at"],
        }

    def delete_mailing_list(self, mailing_list_id: int) -> bool:
        with self._connect() as connection:
            trigger_rows = connection.execute(
                "SELECT id FROM mail_triggers WHERE mailing_list_id = %s",
                (int(mailing_list_id),),
            ).fetchall()
            for trigger_row in trigger_rows:
                connection.execute("DELETE FROM trigger_events WHERE trigger_id = %s", (trigger_row["id"],))
            connection.execute("DELETE FROM mail_triggers WHERE mailing_list_id = %s", (int(mailing_list_id),))
            cursor = connection.execute("DELETE FROM mailing_lists WHERE id = %s", (int(mailing_list_id),))
        return cursor.rowcount > 0

    def list_mailing_lists(self) -> List[Dict[str, Any]]:
        with self._connect() as connection:
            rows = connection.execute(
                "SELECT id, name, emails, created_at FROM mailing_lists ORDER BY created_at DESC"
            ).fetchall()
        return [
            {
                "id": row["id"],
                "name": row["name"],
                "emails": self._parse_emails(row["emails"]),
                "created_at": row["created_at"],
            }
            for row in rows
        ]

    def require_exists(self, mailing_list_id: int) -> None:
        with self._connect() as connection:
            row = connection.execute(
                "SELECT id FROM mailing_lists WHERE id = %s",
                (int(mailing_list_id),),
            ).fetchone()
        if row is None:
            raise ValueError(f"Selected mailing list {mailing_list_id} does not exist.")

    def _parse_emails(self, emails_text: str) -> List[str]:
        values = re.split(r"[\n,;]+", (emails_text or "").replace(" ", ""))
        parsed = [value.strip() for value in values if value and "@" in value]
        return list(dict.fromkeys(parsed))

    def get_recipients(self, mailing_list_id: int) -> List[str]:
        with self._connect() as connection:
            row = connection.execute(
                "SELECT emails FROM mailing_lists WHERE id = %s",
                (int(mailing_list_id),),
            ).fetchone()
        if row is None:
            logger.warning("Mailing list %s not found while processing a trigger.", mailing_list_id)
            return []
        return self._parse_emails(row["emails"])

    def get_mailing_list(self, mailing_list_id: int) -> Dict[str, Any]:
        with self._connect() as cursor:
            row = cursor.execute(
                "SELECT id, name, emails, created_at FROM mailing_lists WHERE id = %s",
                (mailing_list_id,),
            ).fetchone()
        if row is None:
            raise ValueError("Mailing list not found.")
        return {**row, "emails": self._parse_emails(row["emails"])}
