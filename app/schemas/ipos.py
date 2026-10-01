from datetime import date, datetime
from typing import List, Optional

from pydantic import BaseModel


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
