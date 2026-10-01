import logging
from zoneinfo import ZoneInfo

from apscheduler.schedulers.blocking import BlockingScheduler

from app.jobs.refresh import refresh
from app.core.config import Settings
from app.core.logging import configure_logging
from app.core.container import Container

logger = logging.getLogger(__name__)
TIMEZONE = ZoneInfo("Asia/Kolkata")


def create_scheduler() -> BlockingScheduler:
    logger.info("Creating scheduler for IPO refresh jobs in %s", TIMEZONE)
    scheduler = BlockingScheduler(timezone=TIMEZONE)
    scheduler.add_job(
        refresh,
        trigger="cron",
        day_of_week="mon-fri",
        hour="9,11,13,15",
        minute=30,
        id="ipo-subscription-refresh",
        replace_existing=True,
        coalesce=True,
        max_instances=1,
        misfire_grace_time=60 * 30,
    )
    logger.info("Scheduled IPO refresh jobs: weekdays at 09:30, 11:30, 13:30, and 15:30 IST")
    return scheduler


def main() -> None:
    settings = Settings.from_env()
    configure_logging(settings.log_level)
    resources = Container(settings)
    try:
        resources.start()
    finally:
        resources.close()
    scheduler = create_scheduler()
    logger.info("IPO scheduler started")
    try:
        scheduler.start()
    except (KeyboardInterrupt, SystemExit):
        logger.info("IPO scheduler shutdown requested")


if __name__ == "__main__":
    main()
