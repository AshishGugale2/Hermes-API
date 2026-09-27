# IPO Monitor Backend

Create and activate a virtual environment, then install dependencies:

```sh
python3 -m venv .venv
. .venv/bin/activate
pip install -r requirements.txt
uvicorn app.main:app --reload --port 8000
```

SMTP configuration:

```sh
export SMTP_HOST=smtp.gmail.com
export SMTP_PORT=587
export SMTP_USE_TLS=true
export SMTP_USERNAME=you@gmail.com
export SMTP_PASSWORD="app-password"
export SMTP_FROM="IPO Monitor <ipo-monitor@your-domain.com>"
```

For Gmail, use an App Password instead of your normal account password. If `SMTP_HOST` is unset, the app logs emails instead of sending them so local development does not fail.

Mail alert flow:

- Create a mailing list with one or more comma-separated addresses.
- Create an alert trigger with a threshold such as `> 10` or `>= 5`.
- When a snapshot contains an IPO matching the trigger, a message is sent once for that trigger/IPO pair.
- The trigger event is stored in `trigger_events` so duplicate sends are prevented.

Endpoints:

- `GET /api/health`
- `GET /api/ipos` returns the most recent snapshot and fetches one when none exists.
- `POST /api/ipos/refresh` fetches a new snapshot immediately.
- `GET /api/mailing-lists`, `POST /api/mailing-lists`, `PUT /api/mailing-lists/{id}`, `DELETE /api/mailing-lists/{id}`
- `GET /api/triggers`, `POST /api/triggers`, `PUT /api/triggers/{id}`, `DELETE /api/triggers/{id}`
- `POST /api/triggers/{id}/toggle`
- `POST /api/ipo-alerts/pause`

Run the application scheduler in a separate process to fetch data at 09:30, 11:30, 13:30, and 15:30 IST every weekday:

```sh
./scripts/run_scheduler.sh
```

It writes scheduler output to `backend/logs/scheduler.log`.

End-to-end test scenario:

1. Start the backend and UI locally.
2. Set `SMTP_HOST` to a real SMTP relay or a Gmail SMTP endpoint with an app password.
3. Create a mailing list with your own email address.
4. Create a trigger like `IPO Volume Alert` with `> 10` and the mailing list.
5. Refresh the IPO data or seed a snapshot with an `overall_subscription` above `10` for a company.
6. Confirm the alert is sent once and appears in the trigger events list.
7. Refresh again without changing the value; the same trigger/IPO pair should not resend because the event is tracked as already sent.
8. Pause the IPO by entering its `ipo_id` in the “Stop alerts for IPO” form to suppress notifications for that stock.
