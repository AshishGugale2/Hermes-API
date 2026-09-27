# AGENTS.md

## Project

This directory contains the Hermes IPO backend service.

## Purpose

- FastAPI API for IPO monitoring and alerting
- Repository access for the app data layer
- Scheduler service for periodic refresh tasks
- SMTP-based email notifications

## Working conventions

- Use Python 3.11+ for local development and CI.
- Prefer environment variables over hardcoded credentials.
- Keep secrets out of source control; use `.env` locally and `.env.example` as the documented template.
- Do not commit `.env`, local SQLite data, logs, or generated venv folders.
- Prefer repo-relative paths and generic scripts for Linux/server environments.
- Keep changes compatible with both local dev and production deployment assumptions.

## Commands

- Setup environment:
  - `python3 -m venv .venv`
  - `. .venv/bin/activate`
  - `pip install -r requirements.txt`
- Run app:
  - `uvicorn app.main:app --host 0.0.0.0 --port 8000`
- Run scheduler:
  - `python -m app.scheduler`
- Run tests:
  - `PYTHONPATH=. pytest -q`

## Important files

- `app/main.py` — FastAPI app and CORS config
- `app/repository.py` — DB and mail logic
- `app/scheduler.py` — APScheduler configuration
- `app/refresh.py` — data refresh logic
- `scripts/run_scheduler.sh` — Linux-safe scheduler launcher
- `scripts/run_api.sh` — Linux-safe API launcher
- `.env.example` — template for local environment variables

## Safety rules

- Never commit real SMTP credentials or secrets.
- Never hardcode machine-specific absolute paths.
- Prefer production-safe defaults and environment-driven configuration.
- If you add deployment scripts, keep them portable and generic.
