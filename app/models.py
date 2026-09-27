import logging
from datetime import date, datetime
from typing import List, Optional

from pydantic import BaseModel

logger = logging.getLogger(__name__)


class IpoSubscription(BaseModel):
    id: str
    company: str
    qib_subscription: Optional[float] = None
    nii_subscription: Optional[float] = None
    retail_subscription: Optional[float] = None
    overall_subscription: Optional[float] = None
    closing_date: Optional[date] = None


class MarketStatus(BaseModel):
    is_open: bool
    label: str


class IpoDashboard(BaseModel):
    source_url: str
    fetched_at: datetime
    is_stale: bool
    market: MarketStatus
    ipos: List[IpoSubscription]


class MailingListRequest(BaseModel):
    name: str
    emails: str


class MailingListUpdateRequest(BaseModel):
    name: Optional[str] = None
    emails: Optional[str] = None


class MailingListResult(BaseModel):
    id: int
    name: str
    emails: List[str]
    created_at: Optional[str] = None


class TriggerRequest(BaseModel):
    name: str
    threshold: float
    operator: str
    mailing_list_id: int
    active: bool = True
    description: Optional[str] = None


class TriggerUpdateRequest(BaseModel):
    name: Optional[str] = None
    threshold: Optional[float] = None
    operator: Optional[str] = None
    mailing_list_id: Optional[int] = None
    active: Optional[bool] = None
    description: Optional[str] = None


class TriggerResult(BaseModel):
    id: int
    name: str
    threshold: float
    operator: str
    mailing_list_id: int
    mailing_list_name: Optional[str] = None
    active: bool
    description: Optional[str] = None
    created_at: Optional[str] = None


class TriggerEventResult(BaseModel):
    id: int
    trigger_id: int
    ipo_id: str
    company: str
    trigger_threshold: float
    operator: str
    closing_date: Optional[str] = None
    sent_at: Optional[str] = None
    status: str
    subject: Optional[str] = None
    body: Optional[str] = None
    message: Optional[str] = None


class PauseIpoNotificationRequest(BaseModel):
    ipo_id: str
    paused: bool = True
    reason: Optional[str] = None


class SendIpoEmailRequest(BaseModel):
    ipo_id: str
    company: str
    mailing_list_id: int
    threshold: float = 10.0
    operator: str = ">"
    closing_date: Optional[str] = None

