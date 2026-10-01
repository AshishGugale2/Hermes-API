import logging
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)


class AlertService:
    def __init__(self, database, triggers, mailing_lists, notifications, email):
        self.database = database
        self.triggers = triggers
        self.mailing_lists = mailing_lists
        self.notifications = notifications
        self.email = email

    def process_snapshot_triggers(self, snapshot):
        # Coordinate API workers and the scheduler while evaluating/delivering alerts.
        with self.database.alert_lock() as acquired:
            if not acquired:
                return {"sent_count": 0, "events": []}
            return self._process_snapshot_triggers(snapshot)

    def _process_snapshot_triggers(self, snapshot: Dict[str, Any]) -> Dict[str, Any]:
        self.triggers.clear_orphaned_triggers()
        active_triggers = sorted(
            self.triggers.list_triggers(active_only=True),
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

        email_rows_by_list: Dict[int, List[Dict[str, Any]]] = {}
        events_by_list: Dict[int, List[Dict[str, Any]]] = {}

        for ipo in snapshot.get("ipos", []):
            ipo_id = str(ipo.get("id") or "").strip()
            company = str(ipo.get("company") or "Unknown IPO")
            if not ipo_id:
                logger.warning("Skipping IPO without id while evaluating triggers")
                continue
            if self.notifications.is_ipo_paused(ipo_id):
                logger.info("Skipping IPO %s because it is paused", ipo_id)
                continue

            matched_triggers_by_list: Dict[int, List[Dict[str, Any]]] = {}
            for trigger in active_triggers:
                if self.triggers.event_exists(trigger["id"], ipo_id):
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
                matched_triggers_by_list.setdefault(trigger["mailing_list_id"], []).append(trigger)

            if not matched_triggers_by_list:
                continue

            for mailing_list_id, matched_triggers in matched_triggers_by_list.items():
                recipients = self.mailing_lists.get_recipients(mailing_list_id)
                if not recipients:
                    logger.warning(
                        "Skipping trigger(s) for IPO %s because mailing list %s is empty or missing",
                        ipo_id,
                        mailing_list_id,
                    )
                    continue

                highest_trigger = max(matched_triggers, key=lambda trigger: float(trigger["threshold"]))
                for trigger in matched_triggers:
                    status = "sent" if trigger["id"] == highest_trigger["id"] else "covered_by_higher_trigger"
                    events_by_list.setdefault(mailing_list_id, []).append(
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
                        "IPO %s matched trigger id=%s (%s) for mailing list %s at %.2fx; status=%s",
                        ipo_id,
                        trigger["id"],
                        trigger["name"],
                        mailing_list_id,
                        float(ipo.get("overall_subscription") or 0.0),
                        status,
                    )

                email_rows_by_list.setdefault(mailing_list_id, []).append(
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

        if not email_rows_by_list:
            logger.info("No matching IPO-trigger combinations found in this snapshot")
            return {"sent_count": 0, "events": []}

        sent_count = 0
        recorded_events = []
        for mailing_list_id, email_rows in email_rows_by_list.items():
            recipients = self.mailing_lists.get_recipients(mailing_list_id)
            if not recipients:
                continue
            subject, body = self.email.render_aggregate(email_rows)
            result = self.email.send(recipients, subject, body)
            if result["status"] == "failed":
                logger.warning("Alert delivery failed for mailing list %s; leaving events retryable", mailing_list_id)
                continue
            events = events_by_list[mailing_list_id]
            self.triggers.record_events(events, subject, body, result.get("message"))
            recorded_events.extend({**event, "mailing_list_id": mailing_list_id} for event in events)
            sent_count += 1
        return {"sent_count": sent_count, "events": recorded_events}

    def send_manual_ipo_email(
        self,
        ipo_id: str,
        company: str,
        mailing_list_id: int,
        threshold: float,
        operator: str = ">",
        closing_date: Optional[str] = None,
    ) -> Dict[str, Any]:
        recipients = self.mailing_lists.get_recipients(mailing_list_id)
        if not recipients:
            raise ValueError("The selected mailing list has no recipients.")
        if operator not in {">", ">=", "<", "<=", "=", "=="}:
            raise ValueError("Unsupported trigger operator.")

        subject, body = self.email.render_alert(
            company, {"operator": operator, "threshold": float(threshold)}, closing_date or ""
        )
        send_result = self.email.send(recipients, subject, body)
        return {
            "status": send_result.get("status", "sent"),
            "subject": subject,
            "body": body,
            "recipients": recipients,
            "ipo_id": str(ipo_id),
            "message": send_result.get("message"),
        }

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
