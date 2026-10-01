from typing import Optional

from pydantic import BaseModel


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
