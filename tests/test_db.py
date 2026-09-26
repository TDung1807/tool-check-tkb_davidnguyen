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


if __name__ == "__main__":
    unittest.main()
