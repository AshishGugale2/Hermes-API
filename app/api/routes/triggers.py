from typing import Any, Dict, List

from fastapi import APIRouter, Depends, HTTPException

from app.api.dependencies import get_container
from app.core.container import Container

from app.schemas.triggers import TriggerRequest, TriggerUpdateRequest

router = APIRouter()


@router.get("/api/triggers")
def get_triggers(container: Container = Depends(get_container)) -> List[Dict[str, Any]]:
    return container.triggers.list_triggers()


@router.post("/api/triggers")
def create_trigger(payload: TriggerRequest, container: Container = Depends(get_container)) -> Dict[str, Any]:
    try:
        trigger_id = container.triggers.create_trigger(
            payload.name,
            payload.threshold,
            payload.operator,
            payload.mailing_list_id,
            active=payload.active,
            description=payload.description,
        )
    except ValueError as error:
        raise HTTPException(status_code=400, detail=str(error)) from error
    return {"id": trigger_id, "message": "Trigger created successfully"}


@router.put("/api/triggers/{trigger_id}")
def update_trigger(
    trigger_id: int, payload: TriggerUpdateRequest, container: Container = Depends(get_container)
) -> Dict[str, Any]:
    try:
        updated = container.triggers.update_trigger(
            trigger_id,
            name=payload.name,
            threshold=payload.threshold,
            operator=payload.operator,
            mailing_list_id=payload.mailing_list_id,
            active=payload.active,
            description=payload.description,
        )
    except ValueError as error:
        raise HTTPException(status_code=400, detail=str(error)) from error
    return updated


@router.delete("/api/triggers/{trigger_id}")
def delete_trigger(trigger_id: int, container: Container = Depends(get_container)) -> Dict[str, Any]:
    deleted = container.triggers.delete_trigger(trigger_id)
    if not deleted:
        raise HTTPException(status_code=404, detail="Trigger not found")
    return {"id": trigger_id, "deleted": True}


@router.get("/api/trigger-events")
def get_trigger_events(container: Container = Depends(get_container)) -> List[Dict[str, Any]]:
    return container.triggers.list_trigger_events()


@router.post("/api/triggers/{trigger_id}/toggle")
def toggle_trigger(trigger_id: int, payload: Dict[str, bool], container: Container = Depends(get_container)):
    active = payload.get("active", True)
    if not container.triggers.toggle(trigger_id, active):
        raise HTTPException(status_code=404, detail="Trigger not found")
    return {"id": trigger_id, "active": active}
