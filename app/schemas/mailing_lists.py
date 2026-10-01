from typing import List, Optional

from pydantic import BaseModel


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
