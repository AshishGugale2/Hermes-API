"""Compatibility exports for email templates."""

from app.services.email_templates import render_trigger_email_template, _format_closing_date

__all__ = ["render_trigger_email_template", "_format_closing_date"]
