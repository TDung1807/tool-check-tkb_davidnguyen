import unittest
from unittest.mock import MagicMock, patch

import webhook_app


class WebhookSetupTests(unittest.TestCase):
    def test_tdtu_setup_constructs_client_with_credentials(self) -> None:
        client = MagicMock()
        client.__enter__.return_value = client

        with (
            patch.dict(
                "os.environ",
                {
                    "TELEGRAM_BOT_TOKEN": "test-token",
                    "TELEGRAM_WEBHOOK_SECRET": "test-secret",
                },
                clear=False,
            ),
            patch("webhook_app.verify_init_data", return_value={"id": 123, "username": "student"}),
            patch("tdtu.TDTUClient", return_value=client) as client_factory,
            patch("webhook_app.crypto.encrypt", return_value="encrypted-password"),
            patch("webhook_app.db.upsert_user") as upsert_user,
        ):
            response = webhook_app.setup_tdtu(
                webhook_app.TDTUSetupRequest(
                    init_data="valid-init-data",
                    mssv="student-123",
                    password="secret-password",
                )
            )

        self.assertEqual(response, {"success": True})
        client_factory.assert_called_once_with("student-123", "secret-password")
        client.__enter__.assert_called_once_with()
        client.__exit__.assert_called_once()
        upsert_user.assert_called_once_with(
            123,
            mssv="student-123",
            encrypted_pass="encrypted-password",
            telegram_username="student",
        )


if __name__ == "__main__":
    unittest.main()
