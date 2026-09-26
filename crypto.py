"""crypto.py – Fernet encryption for stored credentials.

All user secrets (TDTU passwords, Google OAuth refresh tokens) are encrypted
at rest using a single server-side Fernet key.  The key MUST be kept in an
environment variable and never committed to source control.

Usage::

    from crypto import encrypt, decrypt

    cipher = encrypt("my_secret_password")
    plain  = decrypt(cipher)
"""

from __future__ import annotations

import logging
import os

from cryptography.fernet import Fernet, InvalidToken

logger = logging.getLogger(__name__)

_fernet: Fernet | None = None


class EncryptionKeyMissing(RuntimeError):
    """Raised when ENCRYPTION_KEY is not configured."""


class DecryptionError(RuntimeError):
    """Raised when a ciphertext cannot be decrypted."""


def _get_fernet() -> Fernet:
    """Return a cached Fernet instance using ``ENCRYPTION_KEY`` from env."""
    global _fernet
    if _fernet is not None:
        return _fernet

    key = os.environ.get("ENCRYPTION_KEY", "").strip()
    if not key:
        raise EncryptionKeyMissing(
            "ENCRYPTION_KEY environment variable is required but not set. "
            "Generate one with: python -c "
            "\"from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())\""
        )

    try:
        _fernet = Fernet(key.encode() if isinstance(key, str) else key)
    except (ValueError, Exception) as exc:
        raise EncryptionKeyMissing(
            f"ENCRYPTION_KEY is not a valid Fernet key: {exc}"
        ) from exc

    return _fernet


def encrypt(plaintext: str) -> str:
    """Encrypt *plaintext* and return a URL-safe base64 ciphertext string."""
    f = _get_fernet()
    return f.encrypt(plaintext.encode("utf-8")).decode("ascii")


def decrypt(ciphertext: str) -> str:
    """Decrypt a Fernet *ciphertext* string back to plaintext.

    Raises :class:`DecryptionError` if the ciphertext is invalid or the key
    does not match.
    """
    f = _get_fernet()
    try:
        return f.decrypt(ciphertext.encode("ascii")).decode("utf-8")
    except (InvalidToken, Exception) as exc:
        raise DecryptionError("Failed to decrypt value.") from exc


def reset_cache() -> None:
    """Clear the cached Fernet instance (useful for testing)."""
    global _fernet
    _fernet = None
