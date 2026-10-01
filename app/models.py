"""Compatibility exports for API schemas."""

from app.schemas.ipos import IpoSubscription, MarketStatus, IpoDashboard
from app.schemas.mailing_lists import MailingListRequest, MailingListUpdateRequest, MailingListResult
from app.schemas.triggers import TriggerRequest, TriggerUpdateRequest, TriggerResult, TriggerEventResult
from app.schemas.notifications import PauseIpoNotificationRequest, SendIpoEmailRequest

__all__ = [
    "IpoSubscription",
    "MarketStatus",
    "IpoDashboard",
    "MailingListRequest",
    "MailingListUpdateRequest",
    "MailingListResult",
    "TriggerRequest",
    "TriggerUpdateRequest",
    "TriggerResult",
    "TriggerEventResult",
    "PauseIpoNotificationRequest",
    "SendIpoEmailRequest",
]
