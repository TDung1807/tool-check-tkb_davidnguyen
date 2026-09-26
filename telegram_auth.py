"""telegram_auth.py – Verify Telegram WebApp ``initData``.

When a Telegram Mini App opens, Telegram injects ``initData`` – a query-string
containing user info signed with HMAC-SHA256 using the bot token.  This module
validates that signature so the backend can trust the identity claim.

Reference: https://core.telegram.org/bots/webapps#validating-data-received-via-the-mini-app

Usage::

    from telegram_auth import verify_init_data

    user_data = verify_init_data(raw_init_data, bot_token)
    telegram_id = user_data["id"]
"""

from __future__ import annotations

import hashlib
import hmac
import json
import time
from urllib.parse import parse_qs, unquote


# Maximum age (seconds) of ``auth_date`` before we reject the data.
_MAX_AUTH_AGE_SECONDS = 86_400  # 24 hours


class InitDataError(ValueError):
    """Raised when ``initData`` validation fails."""


def verify_init_data(
    init_data: str,
    bot_token: str,
    *,
    max_age_seconds: int = _MAX_AUTH_AGE_SECONDS,
) -> dict:
    """Validate and parse Telegram WebApp ``initData``.

    Parameters
    ----------
    init_data:
        Raw query-string exactly as provided by ``Telegram.WebApp.initData``.
    bot_token:
        The bot's secret token (from ``TELEGRAM_BOT_TOKEN``).
    max_age_seconds:
        Reject data older than this many seconds.  Set to ``0`` to skip the
        freshness check (useful in tests).

    Returns
    -------
    dict
        Parsed ``user`` object containing at least ``id``, ``first_name``,
        and optionally ``username``, ``last_name``, ``language_code``.

    Raises
    ------
    InitDataError
        If the signature is invalid, data is expired, or required fields
        are missing.
    """
    if not init_data or not bot_token:
        raise InitDataError("initData and bot_token are required.")

    # Parse the query string.
    parsed = parse_qs(init_data, keep_blank_values=True)

    received_hash = _single(parsed, "hash")
    if not received_hash:
        raise InitDataError("Missing 'hash' in initData.")

    # Build the data-check-string (all fields except hash, sorted, joined by \n).
    check_pairs: list[str] = []
    for key in sorted(parsed):
        if key == "hash":
            continue
        # parse_qs returns lists; Telegram sends single values.
        value = parsed[key][0] if parsed[key] else ""
        check_pairs.append(f"{key}={value}")

    data_check_string = "\n".join(check_pairs)

    # HMAC verification: secret_key = HMAC-SHA256("WebAppData", bot_token)
    secret_key = hmac.new(
        b"WebAppData", bot_token.encode("utf-8"), hashlib.sha256
    ).digest()
    expected_hash = hmac.new(
        secret_key, data_check_string.encode("utf-8"), hashlib.sha256
    ).hexdigest()

    if not hmac.compare_digest(received_hash, expected_hash):
        raise InitDataError("initData signature verification failed.")

    # Freshness check.
    auth_date_str = _single(parsed, "auth_date")
    if not auth_date_str:
        raise InitDataError("Missing 'auth_date' in initData.")
    try:
        auth_date = int(auth_date_str)
    except ValueError as exc:
        raise InitDataError("Invalid 'auth_date' value.") from exc

    if max_age_seconds > 0:
        age = int(time.time()) - auth_date
        if age > max_age_seconds:
            raise InitDataError(
                f"initData expired ({age}s old, max {max_age_seconds}s)."
            )

    # Extract user object.
    user_raw = _single(parsed, "user")
    if not user_raw:
        raise InitDataError("Missing 'user' in initData.")

    try:
        user = json.loads(unquote(user_raw))
    except (json.JSONDecodeError, TypeError) as exc:
        raise InitDataError("Invalid 'user' JSON in initData.") from exc

    if not isinstance(user, dict) or "id" not in user:
        raise InitDataError("'user' object missing 'id'.")

    return user


def _single(parsed: dict[str, list[str]], key: str) -> str | None:
    """Return the first value for *key* or ``None``."""
    values = parsed.get(key)
    if not values:
        return None
    return values[0]
