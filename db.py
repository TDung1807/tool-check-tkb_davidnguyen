"""db.py – Supabase persistence layer for multi-user bot.

Provides CRUD helpers for the ``users``, ``sync_snapshots``, and
``sync_logs`` tables.  All functions are synchronous (the Supabase Python
client uses ``httpx`` internally but exposes a sync API).

Environment variables::

    SUPABASE_URL  – e.g. https://xxx.supabase.co
    SUPABASE_KEY  – anon / service-role key
"""

from __future__ import annotations

import datetime as dt
import logging
import os
from dataclasses import dataclass, field

from supabase import Client, create_client

logger = logging.getLogger(__name__)

_client: Client | None = None


# ---------------------------------------------------------------------------
# Data classes
# ---------------------------------------------------------------------------

@dataclass
class User:
    """Represents a row in the ``users`` table."""

    telegram_id: int
    mssv: str
    encrypted_pass: str
    telegram_username: str | None = None
    google_refresh_token: str | None = None  # Fernet encrypted
    google_calendar_id: str | None = None
    is_active: bool = True
    created_at: str | None = None
    last_sync_at: str | None = None

    @property
    def is_fully_setup(self) -> bool:
        """Return ``True`` when both TDTU and Google Calendar are connected."""
        return bool(self.encrypted_pass and self.google_refresh_token and self.google_calendar_id)

    @property
    def has_tdtu(self) -> bool:
        return bool(self.mssv and self.encrypted_pass)

    @property
    def has_google(self) -> bool:
        return bool(self.google_refresh_token and self.google_calendar_id)


# ---------------------------------------------------------------------------
# Client singleton
# ---------------------------------------------------------------------------

def _get_client() -> Client:
    global _client
    if _client is not None:
        return _client

    url = os.environ.get("SUPABASE_URL", "").strip()
    key = os.environ.get("SUPABASE_KEY", "").strip()

    if not url or not key:
        raise RuntimeError(
            "SUPABASE_URL and SUPABASE_KEY environment variables are required."
        )

    _client = create_client(url, key)
    return _client


def reset_client() -> None:
    """Clear the cached client (for testing)."""
    global _client
    _client = None


# ---------------------------------------------------------------------------
# User CRUD
# ---------------------------------------------------------------------------

def _row_to_user(row: dict) -> User:
    return User(
        telegram_id=int(row["telegram_id"]),
        mssv=row.get("mssv") or "",
        encrypted_pass=row.get("encrypted_pass") or "",
        telegram_username=row.get("telegram_username"),
        google_refresh_token=row.get("google_refresh_token"),
        google_calendar_id=row.get("google_calendar_id"),
        is_active=row.get("is_active", True),
        created_at=row.get("created_at"),
        last_sync_at=row.get("last_sync_at"),
    )


def get_user(telegram_id: int) -> User | None:
    """Fetch a single user by Telegram ID.  Returns ``None`` if not found."""
    client = _get_client()
    result = (
        client.table("users")
        .select("*")
        .eq("telegram_id", telegram_id)
        .maybe_single()
        .execute()
    )
    if not result.data:
        return None
    return _row_to_user(result.data)


def upsert_user(telegram_id: int, **kwargs: object) -> User:
    """Insert or update a user.  Only provided kwargs are written.

    Example::

        upsert_user(12345, mssv="205xxxx", encrypted_pass="gAAAA...")
    """
    client = _get_client()
    data: dict[str, object] = {"telegram_id": telegram_id, **kwargs}

    result = (
        client.table("users")
        .upsert(data, on_conflict="telegram_id")
        .execute()
    )

    if not result.data:
        raise RuntimeError("Supabase upsert returned no data.")
    return _row_to_user(result.data[0])


def get_all_active_users() -> list[User]:
    """Return all users where ``is_active`` is true and setup is complete."""
    client = _get_client()
    result = (
        client.table("users")
        .select("*")
        .eq("is_active", True)
        .not_.is_("google_refresh_token", "null")
        .not_.is_("google_calendar_id", "null")
        .execute()
    )
    return [_row_to_user(row) for row in (result.data or [])]


def deactivate_user(telegram_id: int) -> None:
    """Soft-delete: mark user as inactive and clear credentials."""
    client = _get_client()
    client.table("users").update({
        "is_active": False,
        "encrypted_pass": "",
        "google_refresh_token": None,
        "google_calendar_id": None,
    }).eq("telegram_id", telegram_id).execute()
    logger.info("User %s deactivated.", telegram_id)


def update_last_sync(telegram_id: int) -> None:
    """Touch ``last_sync_at`` timestamp."""
    client = _get_client()
    client.table("users").update({
        "last_sync_at": dt.datetime.now(dt.timezone.utc).isoformat(),
    }).eq("telegram_id", telegram_id).execute()


# ---------------------------------------------------------------------------
# Sync snapshots (change detection)
# ---------------------------------------------------------------------------

def get_snapshot(telegram_id: int) -> dict | None:
    """Return the latest sync snapshot for a user, or ``None``."""
    client = _get_client()
    result = (
        client.table("sync_snapshots")
        .select("*")
        .eq("telegram_id", telegram_id)
        .maybe_single()
        .execute()
    )
    return result.data if result.data else None


def save_snapshot(
    telegram_id: int,
    schedule_hash: str,
    schedule_data: str | None = None,
) -> None:
    """Upsert the sync snapshot for change detection."""
    client = _get_client()
    data: dict[str, object] = {
        "telegram_id": telegram_id,
        "schedule_hash": schedule_hash,
        "updated_at": dt.datetime.now(dt.timezone.utc).isoformat(),
    }
    if schedule_data is not None:
        data["schedule_data"] = schedule_data

    client.table("sync_snapshots").upsert(
        data, on_conflict="telegram_id"
    ).execute()


# ---------------------------------------------------------------------------
# Sync logs
# ---------------------------------------------------------------------------

def log_sync(
    telegram_id: int,
    status: str,
    message: str | None = None,
    *,
    sync_type: str = "morning",
) -> None:
    """Insert a sync log entry."""
    client = _get_client()
    client.table("sync_logs").insert({
        "telegram_id": telegram_id,
        "sync_type": sync_type,
        "status": status,
        "message": (message or "")[:500],
    }).execute()
