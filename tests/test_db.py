import unittest
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import db


class DbUserLookupTests(unittest.TestCase):
    def test_get_user_returns_none_for_empty_supabase_response(self) -> None:
        query = MagicMock()
        query.execute.return_value = None
        client = MagicMock()
        client.table.return_value.select.return_value.eq.return_value.maybe_single.return_value = query

        with patch.object(db, "_get_client", return_value=client):
            self.assertIsNone(db.get_user(123))

    def test_get_user_returns_none_for_response_without_data(self) -> None:
        query = MagicMock()
        query.execute.return_value = SimpleNamespace(data=None)
        client = MagicMock()
        client.table.return_value.select.return_value.eq.return_value.maybe_single.return_value = query

        with patch.object(db, "_get_client", return_value=client):
            self.assertIsNone(db.get_user(123))

    def test_upsert_user_updates_existing_row_without_null_required_fields(self) -> None:
        existing = db.User(
            telegram_id=123,
            mssv="20500001",
            encrypted_pass="encrypted-password",
        )
        updated_row = {
            "telegram_id": 123,
            "mssv": "20500001",
            "encrypted_pass": "encrypted-password",
            "google_refresh_token": "encrypted-refresh-token",
            "google_calendar_id": "calendar-id",
        }
        update_query = MagicMock()
        update_query.execute.return_value = SimpleNamespace(data=[updated_row])
        client = MagicMock()
        client.table.return_value.update.return_value.eq.return_value = update_query

        with patch.object(db, "_get_client", return_value=client), patch.object(
            db, "get_user", return_value=existing
        ):
            user = db.upsert_user(
                123,
                google_refresh_token="encrypted-refresh-token",
                google_calendar_id="calendar-id",
            )

        self.assertEqual(user.mssv, "20500001")
        self.assertEqual(user.google_calendar_id, "calendar-id")
        client.table.return_value.update.assert_called_once_with(
            {
                "google_refresh_token": "encrypted-refresh-token",
                "google_calendar_id": "calendar-id",
            }
        )


if __name__ == "__main__":
    unittest.main()
