import logging
import os
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Dict, List

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
import httpx
from dotenv import load_dotenv

from .models import (
    IpoDashboard,
    MailingListRequest,
    MailingListUpdateRequest,
    MarketStatus,
    PauseIpoNotificationRequest,
    SendIpoEmailRequest,
    TriggerRequest,
    TriggerUpdateRequest,
)
from .repository import SnapshotRepository
from .scraper import SOURCE_URL, SourceFormatError, fetch_subscriptions

logger = logging.getLogger(__name__)

logging.basicConfig(
    level=logging.DEBUG,
    format="%(name)s %(message)s",
)

ROOT_DIR = Path(__file__).resolve().parents[1]
load_dotenv(ROOT_DIR / ".env", override=False)
repository = SnapshotRepository(ROOT_DIR / "data" / "ipo_monitor.db")
cache_minutes = int(os.getenv("IPO_CACHE_MINUTES", "15"))

app = FastAPI(title="IPO Monitor API", version="0.1.0")
app.add_middleware(
    CORSMiddleware,
    allow_origins=os.getenv("CORS_ORIGINS", "http://localhost:5173").split(","),
    allow_credentials=False,
    allow_methods=["GET", "POST", "PATCH", "PUT", "DELETE"],
    allow_headers=["*"],
)


@app.get("/api/health")
def health() -> Dict[str, str]:
    logger.info("Health check requested")
    return {"status": "ok"}


@app.get("/api/ipos", response_model=IpoDashboard)
def get_ipos() -> Dict[str, object]:
    logger.info("IPO dashboard request received")
    snapshot = repository.latest_snapshot()
    if snapshot is None:
        logger.warning("No cached IPO snapshot found; refreshing source data")
        return _refresh_or_raise()

    stale = _snapshot_is_stale(snapshot)
    logger.info("Returning cached IPO snapshot; stale=%s", stale)
    return _dashboard(snapshot, is_stale=stale)


@app.post("/api/ipos/refresh", response_model=IpoDashboard)
def refresh_ipos() -> Dict[str, object]:
    logger.info("Manual IPO refresh triggered")
    return _refresh_or_raise()


@app.get("/api/mailing-lists")
def get_mailing_lists() -> List[Dict[str, Any]]:
    logger.info("Mailing list request received")
    return repository.list_mailing_lists()


@app.post("/api/mailing-lists")
def create_mailing_list(payload: MailingListRequest) -> Dict[str, Any]:
    try:
        mailing_list_id = repository.create_mailing_list(payload.name, payload.emails)
    except ValueError as error:
        raise HTTPException(status_code=400, detail=str(error)) from error
    return {"id": mailing_list_id, "name": payload.name, "emails": repository.list_mailing_lists()[-1]["emails"]}


@app.put("/api/mailing-lists/{mailing_list_id}")
def update_mailing_list(mailing_list_id: int, payload: MailingListUpdateRequest) -> Dict[str, Any]:
    try:
        updated = repository.update_mailing_list(
            mailing_list_id,
            name=payload.name,
            emails=payload.emails,
        )
    except ValueError as error:
        raise HTTPException(status_code=400, detail=str(error)) from error
    return updated


@app.delete("/api/mailing-lists/{mailing_list_id}")
def delete_mailing_list(mailing_list_id: int) -> Dict[str, Any]:
    deleted = repository.delete_mailing_list(mailing_list_id)
    if not deleted:
        raise HTTPException(status_code=404, detail="Mailing list not found")
    return {"id": mailing_list_id, "deleted": True}


@app.get("/api/triggers")
def get_triggers() -> List[Dict[str, Any]]:
    return repository.list_triggers()


@app.post("/api/triggers")
def create_trigger(payload: TriggerRequest) -> Dict[str, Any]:
    try:
        trigger_id = repository.create_trigger(
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


@app.put("/api/triggers/{trigger_id}")
def update_trigger(trigger_id: int, payload: TriggerUpdateRequest) -> Dict[str, Any]:
    try:
        updated = repository.update_trigger(
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


@app.delete("/api/triggers/{trigger_id}")
def delete_trigger(trigger_id: int) -> Dict[str, Any]:
    deleted = repository.delete_trigger(trigger_id)
    if not deleted:
        raise HTTPException(status_code=404, detail="Trigger not found")
    return {"id": trigger_id, "deleted": True}


@app.post("/api/triggers/{trigger_id}/toggle")
def toggle_trigger(trigger_id: int, payload: Dict[str, bool]) -> Dict[str, Any]:
    active = payload.get("active", True)
    with repository._connect() as connection:
        cursor = connection.execute(
            "UPDATE mail_triggers SET active = ? WHERE id = ?",
            (1 if active else 0, trigger_id),
        )
        if cursor.rowcount == 0:
            raise HTTPException(status_code=404, detail="Trigger not found")
    return {"id": trigger_id, "active": active}


@app.get("/api/trigger-events")
def get_trigger_events() -> List[Dict[str, Any]]:
    return repository.list_trigger_events()


@app.post("/api/ipo-alerts/pause")
def pause_ipo_alerts(payload: PauseIpoNotificationRequest) -> Dict[str, Any]:
    if not payload.ipo_id:
        raise HTTPException(status_code=400, detail="IPO id is required")
    return repository.pause_ipo_notifications(payload.ipo_id, payload.paused, payload.reason)


@app.post("/api/ipos/send-email")
def send_ipo_email(payload: SendIpoEmailRequest) -> Dict[str, Any]:
    if not payload.company:
        raise HTTPException(status_code=400, detail="IPO company is required")
    try:
        result = repository.send_manual_ipo_email(
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


@app.get("/api/ipo-alerts")
def get_ipo_alert_state() -> List[Dict[str, Any]]:
    with repository._connect() as connection:
        rows = connection.execute(
            "SELECT ipo_id, paused, reason, paused_at, updated_at FROM ipo_notifications ORDER BY updated_at DESC"
        ).fetchall()
    return [
        {
            "ipo_id": row["ipo_id"],
            "paused": bool(row["paused"]),
            "reason": row["reason"],
            "paused_at": row["paused_at"],
            "updated_at": row["updated_at"],
        }
        for row in rows
    ]


def _refresh_or_raise() -> Dict[str, object]:
    try:
        logger.info("Refreshing IPO subscriptions from %s", SOURCE_URL)
        snapshot = repository.save_snapshot(SOURCE_URL, fetch_subscriptions())
        logger.info("IPO snapshot refreshed successfully with %d records", len(snapshot["ipos"]))
    except (httpx.HTTPError, SourceFormatError, OSError, ValueError) as error:
        logger.exception("IPO refresh failed while fetching source data")
        raise HTTPException(status_code=502, detail=f"Subscription source unavailable: {error}") from error
    return _dashboard(snapshot, is_stale=False)


def _dashboard(snapshot: Dict[str, object], is_stale: bool) -> Dict[str, object]:
    now = datetime.now(timezone.utc)
    market_is_open = now.weekday() < 5
    dashboard = {
        **snapshot,
        "fetched_at": snapshot["fetched_at"],
        "is_stale": is_stale,
        "market": MarketStatus(
            is_open=market_is_open,
            label="Market day" if market_is_open else "Market closed",
        ),
    }
    logger.debug("Dashboard assembled: stale=%s, market_open=%s, items=%d", is_stale, market_is_open, len(snapshot.get("ipos", [])))
    return dashboard


def _snapshot_is_stale(snapshot: Dict[str, object]) -> bool:
    fetched_at = datetime.fromisoformat(str(snapshot["fetched_at"]))
    stale = datetime.now(timezone.utc) - fetched_at > timedelta(minutes=cache_minutes)
    logger.debug("Snapshot age check: fetched_at=%s, cache_minutes=%s, stale=%s", fetched_at, cache_minutes, stale)
    return stale
