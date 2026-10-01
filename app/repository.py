"""Legacy facade. New application code uses the repositories and services directly."""

from app.core.config import Settings
from app.core.container import Container


class SnapshotRepository:
    def __init__(self, database_url=None, schema="public"):
        settings = (
            Settings.from_env() if database_url is None else Settings(database_url=database_url, database_schema=schema)
        )
        self.container = Container(settings)
        self.container.start()

    def _connect(self):
        return self.container.database.cursor()

    def close(self):
        self.container.close()

    def __getattr__(self, name):
        aliases = {
            "_validate_mailing_list_exists": "require_exists",
            "_get_recipients_for_trigger": "get_recipients",
            "_event_exists": "event_exists",
            "_build_mail_content": "render_alert",
            "_build_aggregate_mail_content": "render_aggregate",
            "_send_trigger_email": "send",
        }
        name = aliases.get(name, name)
        for component in (
            self.container.ipos,
            self.container.snapshots,
            self.container.mailing_lists,
            self.container.triggers,
            self.container.notifications,
            self.container.alerts,
            self.container.email,
        ):
            if hasattr(component, name):
                return getattr(component, name)
        raise AttributeError(name)
