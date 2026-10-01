import logging
from contextlib import asynccontextmanager

import psycopg2
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from starlette.concurrency import run_in_threadpool

from app.api.routes import health, ipos, mailing_lists, notifications, triggers
from app.core.config import Settings
from app.core.container import Container
from app.core.logging import configure_logging

logger = logging.getLogger(__name__)


def create_app(settings=None, container=None):
    @asynccontextmanager
    async def lifespan(app):
        resolved_settings = settings or (container.settings if container else Settings.from_env())
        configure_logging(resolved_settings.log_level)
        resources = container or Container(resolved_settings)
        app.state.container = resources
        # Startup and shutdown perform blocking database work outside the event loop.
        try:
            await run_in_threadpool(resources.start)
            yield
        finally:
            await run_in_threadpool(resources.close)

    application = FastAPI(title="IPO Monitor API", version="0.2.0", lifespan=lifespan)
    # Resolve browser origins without opening a database during import.
    if settings is not None:
        origins = settings.cors_origins
    elif container is not None:
        origins = container.settings.cors_origins
    else:
        import os
        from pathlib import Path
        from dotenv import load_dotenv

        load_dotenv(Path(__file__).resolve().parents[1] / ".env", override=False)
        origins = [
            origin.strip() for origin in os.getenv("CORS_ORIGINS", "http://localhost:5173").split(",") if origin.strip()
        ]
    application.add_middleware(
        CORSMiddleware,
        allow_origins=list(origins),
        allow_credentials=False,
        allow_methods=["GET", "POST", "PATCH", "PUT", "DELETE"],
        allow_headers=["*"],
    )
    for router in (health.router, ipos.router, mailing_lists.router, triggers.router, notifications.router):
        application.include_router(router)

    @application.exception_handler(ValueError)
    async def invalid_request(request: Request, error: ValueError):
        return JSONResponse(status_code=400, content={"detail": str(error)})

    @application.exception_handler(psycopg2.IntegrityError)
    async def conflict(request: Request, error: psycopg2.IntegrityError):
        return JSONResponse(status_code=409, content={"detail": "The change conflicts with existing data."})

    @application.exception_handler(psycopg2.Error)
    async def database_error(request: Request, error: psycopg2.Error):
        logger.exception("Database operation failed")
        return JSONResponse(status_code=503, content={"detail": "Database temporarily unavailable"})

    return application


app = create_app()
