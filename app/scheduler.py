"""Compatibility entry point for the scheduler."""

from app.jobs.scheduler import TIMEZONE, create_scheduler, main

__all__ = ["TIMEZONE", "create_scheduler", "main"]

if __name__ == "__main__":
    main()
