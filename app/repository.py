import logging
import os
import re
import smtplib
import sqlite3
from datetime import datetime, timezone
from email.message import EmailMessage
from pathlib import Path
from typing import Any, Dict, List, Optional

from app.mail_templates import render_trigger_email_template

logger = logging.getLogger(__name__)


class SnapshotRepository:
    def __init__(self, database_path: Path) -> None:
        self.database_path = database_path
        self.database_path.parent.mkdir(parents=True, exist_ok=True)
        logger.info("Initializing snapshot repository at %s", self.database_path)
        self._initialize()

    def _connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(str(self.database_path))
        connection.row_factory = sqlite3.Row
        return connection

    def _initialize(self) -> None:
        with self._connect() as connection:
            connection.executescript(
                """
                CREATE TABLE IF NOT EXISTS snapshots (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    fetched_at TEXT NOT NULL,
                    source_url TEXT NOT NULL,
                    item_count INTEGER NOT NULL
                );

                CREATE TABLE IF NOT EXISTS ipo_subscriptions (
                    snapshot_id INTEGER NOT NULL,
                    ipo_id TEXT NOT NULL,
                    company TEXT NOT NULL,
                    qib_subscription REAL,
                    nii_subscription REAL,
                    retail_subscription REAL,
                    overall_subscription REAL,
                    closing_date DATE,
                    FOREIGN KEY (snapshot_id) REFERENCES snapshots(id)
                );

                CREATE TABLE IF NOT EXISTS mailing_lists (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    name TEXT NOT NULL UNIQUE,
                    emails TEXT NOT NULL,
                    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
                );

                CREATE TABLE IF NOT EXISTS mail_triggers (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    name TEXT NOT NULL,
                    trigger_type TEXT NOT NULL DEFAULT 'overall_subscription',
                    threshold REAL NOT NULL,
                    operator TEXT NOT NULL CHECK(operator IN ('>', '>=', '<', '<=', '=', '==')),
                    mailing_list_id INTEGER NOT NULL,
                    active INTEGER NOT NULL DEFAULT 1,
                    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                    description TEXT,
                    FOREIGN KEY (mailing_list_id) REFERENCES mailing_lists(id)
                );

                CREATE TABLE IF NOT EXISTS trigger_events (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    trigger_id INTEGER NOT NULL,
                    ipo_id TEXT NOT NULL,
                    company TEXT NOT NULL,
                    trigger_threshold REAL NOT NULL,
                    operator TEXT NOT NULL,
                    closing_date TEXT,
                    sent_at TEXT NOT NULL,
                    status TEXT NOT NULL DEFAULT 'sent',
                    subject TEXT,
                    body TEXT,
                    message TEXT,
                    UNIQUE (trigger_id, ipo_id)
                );

                CREATE TABLE IF NOT EXISTS ipo_notifications (
                    ipo_id TEXT PRIMARY KEY,
                    paused INTEGER NOT NULL DEFAULT 0,
                    paused_at TEXT,
                    reason TEXT,
                    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
                );
                """
            )
            columns = connection.execute(
                "PRAGMA table_info(ipo_subscriptions)"
            ).fetchall()
            has_closing_date = any(column[1] == "closing_date" for column in columns)
            if not has_closing_date:
                logger.info("Adding closing_date column to existing ipo_subscriptions table")
                connection.execute("ALTER TABLE ipo_subscriptions ADD COLUMN closing_date DATE")
        logger.info("Snapshot tables verified for %s", self.database_path)

    def save_snapshot(self, source_url: str, ipos: List[Dict[str, object]]) -> Dict[str, object]:
        sorted_ipos = sorted(
            ipos,
            key=lambda ipo: (
                -(float(ipo.get("overall_subscription")) if ipo.get("overall_subscription") is not None else float("-inf")),
                str(ipo.get("company") or ""),
            ),
        )
        logger.info(sorted_ipos[0] if sorted_ipos else "No IPOs available")
        fetched_at = datetime.now(timezone.utc).isoformat()
        logger.info("Saving IPO snapshot for %s with %d records", source_url, len(sorted_ipos))
        with self._connect() as connection:
            cursor = connection.execute(
                "INSERT INTO snapshots (fetched_at, source_url, item_count) VALUES (?, ?, ?)",
                (fetched_at, source_url, len(sorted_ipos)),
            )
            snapshot_id = cursor.lastrowid
            connection.executemany(
                """
                INSERT INTO ipo_subscriptions (
                    snapshot_id, ipo_id, company, qib_subscription, nii_subscription,
                    retail_subscription, overall_subscription, closing_date
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
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
        trigger_summary = self.process_snapshot_triggers(snapshot)
        snapshot["trigger_summary"] = trigger_summary
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
                WHERE snapshot_id = ?
                ORDER BY overall_subscription DESC, company ASC
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
                    "closing_date": row["closing_date"],
                }
                for row in rows
            ],
        }
        logger.debug("Loaded latest snapshot with %d IPOs", len(result["ipos"]))
        return result

    def create_mailing_list(self, name: str, emails: str) -> int:
        cleaned_name = (name or "").strip()
        if not cleaned_name:
            raise ValueError("A mailing list name is required.")
        recipient_list = self._parse_emails(emails)
        if not recipient_list:
            raise ValueError("Add at least one recipient email address.")
        with self._connect() as connection:
            cursor = connection.execute(
                "INSERT INTO mailing_lists (name, emails) VALUES (?, ?)",
                (cleaned_name, ", ".join(recipient_list)),
            )
        logger.info("Created mailing list %s with %d recipients", cleaned_name, len(recipient_list))
        return int(cursor.lastrowid)

    def update_mailing_list(self, mailing_list_id: int, name: Optional[str] = None, emails: Optional[str] = None) -> Dict[str, Any]:
        with self._connect() as connection:
            row = connection.execute(
                "SELECT id, name, emails, created_at FROM mailing_lists WHERE id = ?",
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
                "UPDATE mailing_lists SET name = ?, emails = ? WHERE id = ?",
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
                "SELECT id FROM mail_triggers WHERE mailing_list_id = ?",
                (int(mailing_list_id),),
            ).fetchall()
            for trigger_row in trigger_rows:
                connection.execute("DELETE FROM trigger_events WHERE trigger_id = ?", (trigger_row["id"],))
            connection.execute("DELETE FROM mail_triggers WHERE mailing_list_id = ?", (int(mailing_list_id),))
            cursor = connection.execute("DELETE FROM mailing_lists WHERE id = ?", (int(mailing_list_id),))
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

    def _validate_mailing_list_exists(self, mailing_list_id: int) -> None:
        with self._connect() as connection:
            row = connection.execute(
                "SELECT id FROM mailing_lists WHERE id = ?",
                (int(mailing_list_id),),
            ).fetchone()
        if row is None:
            raise ValueError(f"Selected mailing list {mailing_list_id} does not exist.")

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
                connection.execute("DELETE FROM trigger_events WHERE trigger_id = ?", (row["id"],))
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
        self._validate_mailing_list_exists(int(mailing_list_id))
        with self._connect() as connection:
            cursor = connection.execute(
                """
                INSERT INTO mail_triggers (name, threshold, operator, mailing_list_id, active, description)
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                (cleaned_name, float(threshold), operator, int(mailing_list_id), 1 if active else 0, description),
            )
        logger.info("Created trigger %s for mailing list %s", cleaned_name, mailing_list_id)
        return int(cursor.lastrowid)

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
                "SELECT id, name, threshold, operator, mailing_list_id, active, description, created_at FROM mail_triggers WHERE id = ?",
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

        with self._connect() as connection:
            connection.execute(
                """
                UPDATE mail_triggers
                SET name = ?, threshold = ?, operator = ?, mailing_list_id = ?, active = ?, description = ?
                WHERE id = ?
                """,
                (
                    updated_name,
                    float(threshold) if threshold is not None else float(row["threshold"]),
                    updated_operator,
                    int(mailing_list_id) if mailing_list_id is not None else int(row["mailing_list_id"]),
                    1 if active is None else 1 if active else 0,
                    description if description is not None else row["description"],
                    int(trigger_id),
                ),
            )
        active_value = row["active"] if active is None else (1 if active else 0)
        target_list_id = int(mailing_list_id) if mailing_list_id is not None else int(row["mailing_list_id"])
        self._validate_mailing_list_exists(target_list_id)
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
            cursor = connection.execute("DELETE FROM trigger_events WHERE trigger_id = ?", (int(trigger_id),))
            cursor = connection.execute("DELETE FROM mail_triggers WHERE id = ?", (int(trigger_id),))
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
            base_query += " WHERE t.active = 1"
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

    def pause_ipo_notifications(self, ipo_id: str, paused: bool = True, reason: Optional[str] = None) -> Dict[str, Any]:
        normalized_ipo_id = str(ipo_id).strip()
        if not normalized_ipo_id:
            raise ValueError("An IPO id is required.")
        with self._connect() as connection:
            connection.execute(
                """
                INSERT INTO ipo_notifications (ipo_id, paused, paused_at, reason, updated_at)
                VALUES (?, ?, ?, ?, ?)
                ON CONFLICT(ipo_id)
                DO UPDATE SET paused = excluded.paused,
                              paused_at = excluded.paused_at,
                              reason = excluded.reason,
                              updated_at = excluded.updated_at
                """,
                (
                    normalized_ipo_id,
                    1 if paused else 0,
                    datetime.now(timezone.utc).isoformat() if paused else None,
                    reason,
                    datetime.now(timezone.utc).isoformat(),
                ),
            )
        return {"ipo_id": normalized_ipo_id, "paused": paused, "reason": reason}

    def is_ipo_paused(self, ipo_id: str) -> bool:
        with self._connect() as connection:
            row = connection.execute(
                "SELECT paused FROM ipo_notifications WHERE ipo_id = ? LIMIT 1",
                (str(ipo_id),),
            ).fetchone()
        return bool(row["paused"]) if row else False

    def list_trigger_events(self, trigger_id: Optional[int] = None) -> List[Dict[str, Any]]:
        query = """
            SELECT id, trigger_id, ipo_id, company, trigger_threshold, operator, closing_date,
                   sent_at, status, subject, body, message
            FROM trigger_events
        """
        params: List[Any] = []
        if trigger_id is not None:
            query += " WHERE trigger_id = ?"
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

    def process_snapshot_triggers(self, snapshot: Dict[str, Any]) -> Dict[str, Any]:
        self.clear_orphaned_triggers()
        active_triggers = sorted(
            self.list_triggers(active_only=True),
            key=lambda trigger: (float(trigger["threshold"]), str(trigger["name"])),
            reverse=True,
        )
        logger.info(
            "Evaluating %d active trigger(s) against %d IPO record(s)",
            len(active_triggers),
            len(snapshot.get("ipos", [])),
        )
        if not active_triggers:
            logger.info("No active triggers available for evaluation")
            return {"sent_count": 0, "events": []}

        email_rows: List[Dict[str, Any]] = []
        all_recipients: List[str] = []
        event_rows: List[Dict[str, Any]] = []

        for ipo in snapshot.get("ipos", []):
            ipo_id = str(ipo.get("id") or "").strip()
            company = str(ipo.get("company") or "Unknown IPO")
            if not ipo_id:
                logger.warning("Skipping IPO without id while evaluating triggers")
                continue
            if self.is_ipo_paused(ipo_id):
                logger.info("Skipping IPO %s because it is paused", ipo_id)
                continue

            matched_triggers: List[Dict[str, Any]] = []
            for trigger in active_triggers:
                if self._event_exists(trigger["id"], ipo_id):
                    logger.info(
                        "Skipping trigger id=%s for IPO %s because it already has a logged event",
                        trigger["id"],
                        ipo_id,
                    )
                    continue
                market_value = float(ipo.get("overall_subscription") or 0.0)
                if not self._matches_trigger(market_value, trigger["threshold"], trigger["operator"]):
                    logger.debug(
                        "IPO %s (%s) value %.2fx does not match trigger id=%s %s %.2fx",
                        ipo_id,
                        company,
                        market_value,
                        trigger["id"],
                        trigger["operator"],
                        trigger["threshold"],
                    )
                    continue
                matched_triggers.append(trigger)

            if not matched_triggers:
                continue

            highest_trigger = matched_triggers[0]
            for trigger in matched_triggers:
                recipients = self._get_recipients_for_trigger(trigger["mailing_list_id"])
                if not recipients:
                    logger.warning(
                        "Skipping trigger %s (%s) because mailing list %s is empty or missing",
                        trigger["id"],
                        trigger["name"],
                        trigger["mailing_list_id"],
                    )
                    continue
                all_recipients.extend(recipients)
                status = "sent" if trigger["id"] == highest_trigger["id"] else "covered_by_higher_trigger"
                event_rows.append(
                    {
                        "trigger_id": trigger["id"],
                        "ipo_id": ipo_id,
                        "company": company,
                        "trigger_threshold": trigger["threshold"],
                        "operator": trigger["operator"],
                        "closing_date": str(ipo.get("closing_date") or ""),
                        "status": status,
                    }
                )
                logger.info(
                    "IPO %s matched trigger id=%s (%s) at %.2fx; status=%s",
                    ipo_id,
                    trigger["id"],
                    trigger["name"],
                    float(ipo.get("overall_subscription") or 0.0),
                    status,
                )

            email_rows.append(
                {
                    "id": ipo_id,
                    "company": company,
                    "overall_subscription": float(ipo.get("overall_subscription") or 0.0),
                    "closing_date": str(ipo.get("closing_date") or ""),
                    "triggers": [
                        {
                            "id": trigger["id"],
                            "name": trigger["name"],
                            "operator": trigger["operator"],
                            "threshold": float(trigger["threshold"]),
                        }
                        for trigger in matched_triggers
                    ],
                }
            )

        if not email_rows:
            logger.info("No matching IPO-trigger combinations found in this snapshot")
            return {"sent_count": 0, "events": []}

        recipients = list(dict.fromkeys(all_recipients))
        subject, body = self._build_aggregate_mail_content(email_rows)
        logger.info(
            "Sending one aggregate IPO alert email to %d recipient(s) for %d IPO(s)",
            len(recipients),
            len(email_rows),
        )
        send_result = self._send_trigger_email(recipients, subject, body)

        with self._connect() as connection:
            for event in event_rows:
                connection.execute(
                    """
                    INSERT INTO trigger_events (
                        trigger_id, ipo_id, company, trigger_threshold, operator,
                        closing_date, sent_at, status, subject, body, message
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
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
                        send_result.get("message"),
                    ),
                )

        logger.info("Trigger evaluation complete; one aggregate email sent for %d IPOs", len(email_rows))
        return {"sent_count": 1, "events": event_rows}

    def send_manual_ipo_email(
        self,
        ipo_id: str,
        company: str,
        mailing_list_id: int,
        threshold: float,
        operator: str = ">",
        closing_date: Optional[str] = None,
    ) -> Dict[str, Any]:
        recipients = self._get_recipients_for_trigger(mailing_list_id)
        if not recipients:
            raise ValueError("The selected mailing list has no recipients.")
        if operator not in {">", ">=", "<", "<=", "=", "=="}:
            raise ValueError("Unsupported trigger operator.")

        subject, body = self._build_mail_content(company, {"operator": operator, "threshold": float(threshold)}, closing_date or "")
        send_result = self._send_trigger_email(recipients, subject, body)
        return {
            "status": send_result.get("status", "sent"),
            "subject": subject,
            "body": body,
            "recipients": recipients,
            "ipo_id": str(ipo_id),
            "message": send_result.get("message"),
        }

    def _parse_emails(self, emails_text: str) -> List[str]:
        values = re.split(r"[\n,;]+", (emails_text or "").replace(" ", ""))
        parsed = [value.strip() for value in values if value and "@" in value]
        return list(dict.fromkeys(parsed))

    def _get_recipients_for_trigger(self, mailing_list_id: int) -> List[str]:
        with self._connect() as connection:
            row = connection.execute(
                "SELECT emails FROM mailing_lists WHERE id = ?",
                (int(mailing_list_id),),
            ).fetchone()
        if row is None:
            logger.warning(
                "Trigger references mailing list %s, but that list does not exist. Skipping trigger.",
                mailing_list_id,
            )
            return []
        return self._parse_emails(row["emails"])

    def _matches_trigger(self, current_value: float, threshold: float, operator: str) -> bool:
        if operator == ">":
            return current_value > threshold
        if operator == ">=":
            return current_value >= threshold
        if operator == "<":
            return current_value < threshold
        if operator == "<=":
            return current_value <= threshold
        if operator in {"=", "=="}:
            return current_value == threshold
        return False

    def _event_exists(self, trigger_id: int, ipo_id: str) -> bool:
        with self._connect() as connection:
            row = connection.execute(
                "SELECT 1 FROM trigger_events WHERE trigger_id = ? AND ipo_id = ? LIMIT 1",
                (trigger_id, ipo_id),
            ).fetchone()
        return row is not None

    def _build_mail_content(
        self,
        company: str,
        trigger: Dict[str, Any],
        closing_date: str,
    ) -> tuple[str, str]:
        return render_trigger_email_template(company, trigger, closing_date)

    def _build_aggregate_mail_content(
        self,
        matched_ipos: List[Dict[str, Any]],
    ) -> tuple[str, str]:
        total_matches = len(matched_ipos)
        truncation = "" if total_matches <= 20 else " (showing first 20)"
        visible_rows = matched_ipos[:20]

        rows_html = []
        for ipo in visible_rows:
            trigger_text = " | ".join(
                f"{trigger['operator']} {trigger['threshold']:.2f}x"
                for trigger in ipo["triggers"]
            )
            rows_html.append(
                "<tr>"
                f"<td>{ipo['company']}</td>"
                f"<td>{float(ipo['overall_subscription']):.2f}x</td>"
                f"<td>{trigger_text}</td>"
                f"<td>{ipo['closing_date'] if ipo['closing_date'] else '--'}</td>"
                "</tr>"
            )

        subject = f"IPO Alert: {total_matches} company(s) met the configured thresholds{truncation}"
        body = (
            "<html><body style='font-family:Arial,sans-serif; line-height:1.6; color:#0f172a; padding:24px;'>"
            "<div style='max-width:900px; margin:0 auto; padding:24px; border:1px solid #e2e8f0; border-radius:12px; background:#fff;'>"
            "<h2 style='margin:0 0 12px; color:#0f172a;'>IPO Alert</h2>"
            "<p style='margin:0 0 16px;'>The following companies matched the active trigger rules in the latest refresh.</p>"
            "<table style='width:100%; border-collapse:collapse; font-size:14px;'>"
            "<thead><tr style='background:#f8fafc; text-align:left;'>"
            "<th style='padding:10px 12px; border-bottom:1px solid #e2e8f0;'>Company</th>"
            "<th style='padding:10px 12px; border-bottom:1px solid #e2e8f0;'>Overall</th>"
            "<th style='padding:10px 12px; border-bottom:1px solid #e2e8f0;'>Triggers</th>"
            "<th style='padding:10px 12px; border-bottom:1px solid #e2e8f0;'>Closing date</th>"
            "</tr></thead>"
            f"<tbody>{''.join(rows_html)}</tbody>"
            "</table>"
            "<p style='margin:16px 0 0; color:#475569; font-size:12px;'>This alert was generated automatically.</p>"
            "</div></body></html>"
        )
        return subject, body

    def _get_recipients_for_trigger(self, mailing_list_id: int) -> List[str]:
        with self._connect() as connection:
            row = connection.execute(
                "SELECT emails FROM mailing_lists WHERE id = ?",
                (int(mailing_list_id),),
            ).fetchone()
        if row is None:
            logger.warning("Mailing list %s not found while processing a trigger.", mailing_list_id)
            return []
        return self._parse_emails(row["emails"])

    def _send_trigger_email(self, recipients: List[str], subject: str, body: str) -> Dict[str, Any]:
        host = os.getenv("SMTP_HOST")
        if not host:
            logger.info("SMTP_HOST not configured; logging trigger email for %d recipients", len(recipients))
            return {
                "status": "logged",
                "message": f"Trigger alert queued for {len(recipients)} recipients without SMTP delivery.",
            }

        message = EmailMessage()
        message["Subject"] = subject
        message["From"] = os.getenv("SMTP_FROM", "noreply@ipo-monitor.local")
        message["To"] = ", ".join(recipients)

        plain_text = body
        html_body = body
        if "<html" not in body.lower():
            plain_text = body
            html_body = (
                f"<html><body style='font-family:Arial,sans-serif; line-height:1.6; color:#0f172a; padding:24px;'>"
                f"<div style='max-width:640px; margin:0 auto; padding:24px; border:1px solid #e2e8f0; border-radius:12px;'>"
                f"<h2 style='margin:0 0 12px; color:#0f172a;'>IPO Alert</h2>"
                f"<p>{body}</p>"
                f"</div></body></html>"
            )

        message.set_content(plain_text)
        message.add_alternative(html_body, subtype="html")

        smtp_port = int(os.getenv("SMTP_PORT", "587"))
        use_tls = os.getenv("SMTP_USE_TLS", "true").lower() not in {"false", "0", "no"}
        username = os.getenv("SMTP_USERNAME")
        password = os.getenv("SMTP_PASSWORD")
        logger.info(
            "Attempting SMTP delivery: host=%s port=%s tls=%s recipients=%s sender=%s",
            host,
            smtp_port,
            use_tls,
            recipients,
            message["From"],
        )

        try:
            if use_tls:
                with smtplib.SMTP(host, smtp_port) as client:
                    logger.info("Opening SMTP TLS session to %s:%s", host, smtp_port)
                    client.starttls()
                    if username and password:
                        logger.info("SMTP login attempted with username=%s", username)
                        client.login(username, password)
                    client.send_message(message, from_addr=message["From"], to_addrs=recipients)
            else:
                with smtplib.SMTP(host, smtp_port) as client:
                    if username and password:
                        logger.info("SMTP login attempted with username=%s", username)
                        client.login(username, password)
                    client.send_message(message, from_addr=message["From"], to_addrs=recipients)
            logger.info("SMTP trigger email sent successfully to %d recipient(s)", len(recipients))
            return {"status": "sent", "message": f"Sent to {len(recipients)} recipient(s)."}
        except (smtplib.SMTPException, OSError) as error:
            logger.exception("Failed to send trigger email to %s via SMTP host %s:%s", recipients, host, smtp_port)
            return {"status": "failed", "message": f"SMTP delivery failed: {error}"}
