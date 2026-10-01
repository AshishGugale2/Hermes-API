from typing import Any, Dict, List

from fastapi import APIRouter, Depends, HTTPException

from app.api.dependencies import get_container
from app.core.container import Container

from app.schemas.mailing_lists import MailingListRequest, MailingListUpdateRequest

router = APIRouter()


@router.get("/api/mailing-lists")
def get_mailing_lists(container: Container = Depends(get_container)) -> List[Dict[str, Any]]:
    return container.mailing_lists.list_mailing_lists()


@router.post("/api/mailing-lists")
def create_mailing_list(payload: MailingListRequest, container: Container = Depends(get_container)) -> Dict[str, Any]:
    try:
        mailing_list_id = container.mailing_lists.create_mailing_list(payload.name, payload.emails)
    except ValueError as error:
        raise HTTPException(status_code=400, detail=str(error)) from error
    return container.mailing_lists.get_mailing_list(mailing_list_id)


@router.put("/api/mailing-lists/{mailing_list_id}")
def update_mailing_list(
    mailing_list_id: int, payload: MailingListUpdateRequest, container: Container = Depends(get_container)
) -> Dict[str, Any]:
    try:
        updated = container.mailing_lists.update_mailing_list(
            mailing_list_id,
            name=payload.name,
            emails=payload.emails,
        )
    except ValueError as error:
        raise HTTPException(status_code=400, detail=str(error)) from error
    return updated


@router.delete("/api/mailing-lists/{mailing_list_id}")
def delete_mailing_list(mailing_list_id: int, container: Container = Depends(get_container)) -> Dict[str, Any]:
    deleted = container.mailing_lists.delete_mailing_list(mailing_list_id)
    if not deleted:
        raise HTTPException(status_code=404, detail="Mailing list not found")
    return {"id": mailing_list_id, "deleted": True}
