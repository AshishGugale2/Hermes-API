from datetime import datetime, timedelta, timezone

from app.integrations.subscriptions import SOURCE_URL, fetch_subscriptions


class IpoService:
    def __init__(self, snapshots, alerts, settings):
        self.snapshots = snapshots
        self.alerts = alerts
        self.settings = settings

    def save_snapshot(self, source_url, ipos):
        snapshot = self.snapshots.save_snapshot(source_url, ipos)
        snapshot["trigger_summary"] = self.alerts.process_snapshot_triggers(snapshot)
        return snapshot

    def refresh(self):
        return self.save_snapshot(SOURCE_URL, fetch_subscriptions())

    def dashboard(self):
        snapshot = self.snapshots.latest_snapshot()
        if snapshot is None:
            return self.refresh_dashboard()
        fetched_at = datetime.fromisoformat(str(snapshot["fetched_at"]))
        if fetched_at.tzinfo is None:
            fetched_at = fetched_at.replace(tzinfo=timezone.utc)
        stale = datetime.now(timezone.utc) - fetched_at > timedelta(minutes=self.settings.ipo_cache_minutes)
        return self._dashboard(snapshot, stale)

    def refresh_dashboard(self):
        return self._dashboard(self.refresh(), False)

    def _dashboard(self, snapshot, stale):
        market_is_open = datetime.now(timezone.utc).weekday() < 5
        return {
            **snapshot,
            "is_stale": stale,
            "market": {"is_open": market_is_open, "label": "Market day" if market_is_open else "Market closed"},
        }
