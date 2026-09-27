import logging

from .repository import SnapshotRepository
from .scraper import SOURCE_URL, fetch_subscriptions
from .main import ROOT_DIR

logger = logging.getLogger(__name__)


def refresh() -> None:
    logger.info("Starting IPO refresh task")
    repository = SnapshotRepository(ROOT_DIR / "data" / "ipo_monitor.db")
    snapshot = repository.save_snapshot(SOURCE_URL, fetch_subscriptions())
    logger.info("Saved %d IPO subscriptions at %s", len(snapshot["ipos"]), snapshot["fetched_at"])


def main() -> None:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s %(message)s",
    )
    logger.info("Running manual refresh script")
    refresh()


if __name__ == "__main__":
    main()
