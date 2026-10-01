from typing import Any, Dict

from fastapi import APIRouter, Depends, HTTPException

from app.api.dependencies import get_container
from app.core.container import Container

from app.schemas.notifications import PauseIpoNotificationRequest, SendIpoEmailRequest

router = APIRouter()


@router.post("/api/ipo-alerts/pause")
def pause_ipo_alerts(
    payload: PauseIpoNotificationRequest, container: Container = Depends(get_container)
) -> Dict[str, Any]:
    if not payload.ipo_id:
        raise HTTPException(status_code=400, detail="IPO id is required")
    return container.notifications.pause_ipo_notifications(payload.ipo_id, payload.paused, payload.reason)


@router.post("/api/ipos/send-email")
def send_ipo_email(payload: SendIpoEmailRequest, container: Container = Depends(get_container)) -> Dict[str, Any]:
    if not payload.company:
        raise HTTPException(status_code=400, detail="IPO company is required")
    try:
        result = container.alerts.send_manual_ipo_email(
            ipo_id=payload.ipo_id,
            company=payload.company,
            mailing_list_id=payload.mailing_list_id,
            threshold=payload.threshold,
            operator=payload.operator,
            closing_date=payload.closing_date,
        )
    except ValueError as error:
        raise HTTPException(status_code=400, detail=str(error)) from error
    return result


@router.get("/api/ipo-alerts")
def get_ipo_alert_state(container: Container = Depends(get_container)):
    return container.notifications.list_notifications()
