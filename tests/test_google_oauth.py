"""Isolated tests for Google OAuth and calendar provisioning."""

from unittest.mock import MagicMock, patch

import pytest

import google_oauth


def test_calendar_search_paginates_before_creating():
    service = MagicMock()
    listing = service.calendarList.return_value.list.return_value.execute
    listing.side_effect = [
        {"items": [{"summary": "Other", "id": "other"}], "nextPageToken": "next"},
        {"items": [{"summary": "TDTU Bot", "id": "existing"}]},
    ]
    assert google_oauth.get_or_create_calendar(service) == "existing"
    assert service.calendarList.return_value.list.call_args_list[1].kwargs == {"pageToken": "next"}
    service.calendars.assert_not_called()


def test_calendar_created_when_missing():
    service = MagicMock()
    service.calendarList.return_value.list.return_value.execute.return_value = {"items": []}
    service.calendars.return_value.insert.return_value.execute.return_value = {"id": "new"}
    assert google_oauth.get_or_create_calendar(service) == "new"
    service.calendars.return_value.insert.assert_called_once_with(
        body={"summary": "TDTU Bot", "timeZone": "Asia/Ho_Chi_Minh"}
    )


@patch("google_oauth.get_or_create_calendar", return_value="calendar-id")
@patch("google_oauth.build")
@patch("google_oauth.get_client_config", return_value={})
@patch("google_oauth.Flow.from_client_config")
@patch("google_oauth.crypto.decrypt", return_value="123")
def test_exchange_code_uses_refresh_token(decrypt, flow_factory, config, build, get_calendar):
    flow = flow_factory.return_value
    flow.credentials.refresh_token = "refresh-token"
    assert google_oauth.exchange_code("code", "state", "https://example.test/callback") == ("refresh-token", "calendar-id")
    flow.fetch_token.assert_called_once_with(code="code")
    build.assert_called_once_with("calendar", "v3", credentials=flow.credentials)


@patch("google_oauth.get_client_config", return_value={})
@patch("google_oauth.Flow.from_client_config")
@patch("google_oauth.crypto.decrypt", return_value="123")
def test_exchange_code_rejects_missing_refresh_token(decrypt, flow_factory, config):
    flow_factory.return_value.credentials.refresh_token = None
    with pytest.raises(ValueError, match="refresh token"):
        google_oauth.exchange_code("code", "state", "https://example.test/callback")


def test_exchange_code_rejects_invalid_state_before_token_exchange():
    with patch("google_oauth.crypto.decrypt", side_effect=ValueError("invalid")), patch("google_oauth.Flow.from_client_config") as flow:
        with pytest.raises(ValueError, match="Invalid state"):
            google_oauth.exchange_code("code", "state", "https://example.test/callback")
        flow.assert_not_called()
