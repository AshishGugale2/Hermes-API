from fastapi import APIRouter, Depends, HTTPException

from app.api.dependencies import get_container
from app.core.container import Container

import logging
import psycopg2

router = APIRouter()
logger = logging.getLogger(__name__)


@router.get("/api/health")
def health():
    return {"status": "ok"}


@router.get("/api/health/ready")
def ready(container: Container = Depends(get_container)):
    try:
        container.database.check_ready()
    except (psycopg2.Error, RuntimeError):
        logger.exception("Database readiness check failed")
        raise HTTPException(status_code=503, detail="Database unavailable or migrations pending")
    return {"status": "ok"}
