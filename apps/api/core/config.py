"""Runtime configuration read from the environment."""

import os


class DatabaseNotConfiguredError(RuntimeError):
    """Raised when the market database connection string is missing."""


def database_url() -> str:
    """Connection string for the read-only `uzex_agent` role (Supabase in production)."""
    url = os.environ.get("AGENT_DATABASE_URL", "").strip()
    if not url:
        raise DatabaseNotConfiguredError(
            "AGENT_DATABASE_URL is not set. Point it at the uzex_agent role; see README.md."
        )
    return url
