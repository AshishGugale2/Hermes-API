from dataclasses import dataclass, field
import os
from pathlib import Path
from typing import Optional

from dotenv import load_dotenv


@dataclass(frozen=True)
class Settings:
    database_url: str = field(repr=False)
    database_schema: str = "public"
    db_pool_max: int = 10
    ipo_cache_minutes: int = 15
    cors_origins: tuple = ("http://localhost:5173",)
    log_level: str = "INFO"
    smtp_host: Optional[str] = None
    smtp_port: int = 587
    smtp_use_tls: bool = True
    smtp_username: Optional[str] = field(default=None, repr=False)
    smtp_password: Optional[str] = field(default=None, repr=False)
    smtp_from: str = "noreply@ipo-monitor.local"

    def __post_init__(self):
        if not self.database_url.startswith(("postgresql://", "postgres://")):
            raise ValueError("DATABASE_URL must be a PostgreSQL connection URL.")
        if self.db_pool_max < 2:
            raise ValueError("DB_POOL_MAX must be at least 2 for alert processing.")
        if self.ipo_cache_minutes < 1:
            raise ValueError("IPO_CACHE_MINUTES must be positive.")
        if not 1 <= self.smtp_port <= 65535:
            raise ValueError("SMTP_PORT must be a valid port.")
        if self.log_level not in {"DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"}:
            raise ValueError("LOG_LEVEL must be a standard logging level.")

    @classmethod
    def from_env(cls):
        load_dotenv(Path(__file__).resolve().parents[2] / ".env", override=False)
        return cls(
            database_url=os.getenv("DATABASE_URL", ""),
            database_schema=os.getenv("DATABASE_SCHEMA", "public"),
            db_pool_max=int(os.getenv("DB_POOL_MAX", "10")),
            ipo_cache_minutes=int(os.getenv("IPO_CACHE_MINUTES", "15")),
            cors_origins=tuple(
                origin.strip()
                for origin in os.getenv("CORS_ORIGINS", "http://localhost:5173").split(",")
                if origin.strip()
            ),
            log_level=os.getenv("LOG_LEVEL", "INFO").upper(),
            smtp_host=os.getenv("SMTP_HOST") or None,
            smtp_port=int(os.getenv("SMTP_PORT", "587")),
            smtp_use_tls=os.getenv("SMTP_USE_TLS", "true").lower() not in {"false", "0", "no"},
            smtp_username=os.getenv("SMTP_USERNAME") or None,
            smtp_password=os.getenv("SMTP_PASSWORD") or None,
            smtp_from=os.getenv("SMTP_FROM", "noreply@ipo-monitor.local"),
        )
