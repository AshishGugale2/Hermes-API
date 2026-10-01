from fastapi import APIRouter, Depends, HTTPException

from app.api.dependencies import get_container
from app.core.container import Container

import httpx

from app.integrations.subscriptions import SourceFormatError
from app.schemas.ipos import IpoDashboard

router = APIRouter()


def source_response(operation):
    try:
        return operation()
    except (httpx.HTTPError, SourceFormatError, OSError) as error:
        raise HTTPException(status_code=502, detail="Subscription source unavailable") from error


@router.get("/api/ipos", response_model=IpoDashboard)
def get_ipos(container: Container = Depends(get_container)):
    return source_response(container.ipos.dashboard)


@router.post("/api/ipos/refresh", response_model=IpoDashboard)
def refresh_ipos(container: Container = Depends(get_container)):
    return source_response(container.ipos.refresh_dashboard)
