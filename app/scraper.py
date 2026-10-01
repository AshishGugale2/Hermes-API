"""Compatibility exports for the subscription source client."""

from app.integrations.subscriptions import (
    SOURCE_URL,
    SourceFormatError,
    fetch_subscriptions,
    parse_subscriptions,
    _record_from_api_row,
)

__all__ = ["SOURCE_URL", "SourceFormatError", "fetch_subscriptions", "parse_subscriptions", "_record_from_api_row"]
