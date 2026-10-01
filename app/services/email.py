import logging
import smtplib
from email.message import EmailMessage
from html import escape
from typing import Any, Dict, List

from app.services.email_templates import render_trigger_email_template

logger = logging.getLogger(__name__)


class EmailService:
    def __init__(self, settings):
        self.settings = settings

    def render_alert(
        self,
        company: str,
        trigger: Dict[str, Any],
        closing_date: str,
    ) -> tuple[str, str]:
        return render_trigger_email_template(company, trigger, closing_date)

    def render_aggregate(
        self,
        matched_ipos: List[Dict[str, Any]],
    ) -> tuple[str, str]:
        total_matches = len(matched_ipos)
        truncation = "" if total_matches <= 20 else " (showing first 20)"
        visible_rows = matched_ipos[:20]

        rows_html = []
        for ipo in visible_rows:
            trigger_text = " | ".join(
                f"{trigger['operator']} {trigger['threshold']:.2f}x" for trigger in ipo["triggers"]
            )
            rows_html.append(
                "<tr>"
                f"<td>{escape(str(ipo['company']))}</td>"
                f"<td>{float(ipo['overall_subscription']):.2f}x</td>"
                f"<td>{escape(trigger_text)}</td>"
                f"<td>{escape(str(ipo['closing_date'])) if ipo['closing_date'] else '--'}</td>"
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

    def send(self, recipients: List[str], subject: str, body: str) -> Dict[str, Any]:
        host = self.settings.smtp_host
        if not host:
            logger.info("SMTP_HOST not configured; logging trigger email for %d recipients", len(recipients))
            return {
                "status": "logged",
                "message": f"Trigger alert queued for {len(recipients)} recipients without SMTP delivery.",
            }

        message = EmailMessage()
        message["Subject"] = subject
        message["From"] = self.settings.smtp_from
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

        smtp_port = self.settings.smtp_port
        use_tls = self.settings.smtp_use_tls
        username = self.settings.smtp_username
        password = self.settings.smtp_password
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
                with smtplib.SMTP(host, smtp_port, timeout=30) as client:
                    logger.info("Opening SMTP TLS session to %s:%s", host, smtp_port)
                    client.starttls()
                    if username and password:
                        logger.info("SMTP login attempted with username=%s", username)
                        client.login(username, password)
                    client.send_message(message, from_addr=message["From"], to_addrs=recipients)
            else:
                with smtplib.SMTP(host, smtp_port, timeout=30) as client:
                    if username and password:
                        logger.info("SMTP login attempted with username=%s", username)
                        client.login(username, password)
                    client.send_message(message, from_addr=message["From"], to_addrs=recipients)
            logger.info("SMTP trigger email sent successfully to %d recipient(s)", len(recipients))
            return {"status": "sent", "message": f"Sent to {len(recipients)} recipient(s)."}
        except (smtplib.SMTPException, OSError) as error:
            logger.exception("Failed to send trigger email to %s via SMTP host %s:%s", recipients, host, smtp_port)
            return {"status": "failed", "message": f"SMTP delivery failed: {error}"}
