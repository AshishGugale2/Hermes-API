"""Compatibility entry point for a manual refresh."""

from app.jobs.refresh import refresh, main

__all__ = ["refresh", "main"]

if __name__ == "__main__":
    main()
