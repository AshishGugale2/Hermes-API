from typing import Optional

from pydantic import BaseModel


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
