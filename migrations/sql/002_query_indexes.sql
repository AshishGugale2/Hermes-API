CREATE INDEX IF NOT EXISTS idx_ipo_subscriptions_snapshot ON ipo_subscriptions (snapshot_id);
CREATE INDEX IF NOT EXISTS idx_mail_triggers_mailing_list ON mail_triggers (mailing_list_id);
CREATE INDEX IF NOT EXISTS idx_trigger_events_sent_at ON trigger_events (sent_at DESC);
