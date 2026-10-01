import logging

from app.core.config import Settings
from app.core.container import Container
from app.core.logging import configure_logging

logger = logging.getLogger(__name__)


def refresh():
    settings = Settings.from_env()
    configure_logging(settings.log_level)
    container = Container(settings)
    try:
        container.start()
        snapshot = container.ipos.refresh()
        logger.info("Saved %d IPO subscriptions at %s", len(snapshot["ipos"]), snapshot["fetched_at"])
    finally:
        container.close()


def main():
    refresh()


if __name__ == "__main__":
    main()
