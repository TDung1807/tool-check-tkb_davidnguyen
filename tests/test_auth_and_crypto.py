"""Tests for credential encryption and Telegram Mini App authentication."""

import hashlib
import hmac
import json
from urllib.parse import urlencode
from unittest.mock import patch

import pytest
from cryptography.fernet import Fernet

import crypto
from telegram_auth import InitDataError, verify_init_data


@pytest.fixture(autouse=True)
def reset_crypto_cache():
    crypto.reset_cache()
    yield
    crypto.reset_cache()


def signed_data(token="bot-token", **overrides):
    fields = {"auth_date": "1000", "user": json.dumps({"id": 123, "first_name": "A%22B"})}
    fields.update(overrides)
    check_string = "\n".join(f"{key}={value}" for key, value in sorted(fields.items()))
    secret = hmac.new(b"WebAppData", token.encode(), hashlib.sha256).digest()
    fields["hash"] = hmac.new(secret, check_string.encode(), hashlib.sha256).hexdigest()
    return urlencode(fields)


def test_encrypt_round_trip_and_reject_wrong_key(monkeypatch):
    monkeypatch.setenv("ENCRYPTION_KEY", Fernet.generate_key().decode())
    ciphertext = crypto.encrypt("mật khẩu bí mật")
    assert "mật khẩu" not in ciphertext
    assert crypto.decrypt(ciphertext) == "mật khẩu bí mật"
    monkeypatch.setenv("ENCRYPTION_KEY", Fernet.generate_key().decode())
    crypto.reset_cache()
    with pytest.raises(crypto.DecryptionError):
        crypto.decrypt(ciphertext)


@pytest.mark.parametrize("key", ["", "invalid-key"])
def test_encrypt_requires_valid_key(monkeypatch, key):
    monkeypatch.setenv("ENCRYPTION_KEY", key)
    with pytest.raises(crypto.EncryptionKeyMissing):
        crypto.encrypt("secret")


def test_signed_telegram_user_preserves_literal_percent_encoding():
    with patch("telegram_auth.time.time", return_value=1001):
        assert verify_init_data(signed_data(), "bot-token") == {"id": 123, "first_name": "A%22B"}


def test_telegram_rejects_tampering_and_expiration():
    data = signed_data()
    with pytest.raises(InitDataError, match="signature"):
        verify_init_data(data.replace("1000", "1001"), "bot-token", max_age_seconds=0)
    with patch("telegram_auth.time.time", return_value=2001):
        with pytest.raises(InitDataError, match="expired"):
            verify_init_data(data, "bot-token", max_age_seconds=1000)


@pytest.mark.parametrize("user", ["invalid json", json.dumps({"first_name": "No ID"}), "[]"])
def test_telegram_rejects_invalid_signed_user(user):
    with pytest.raises(InitDataError):
        verify_init_data(signed_data(user=user), "bot-token", max_age_seconds=0)
