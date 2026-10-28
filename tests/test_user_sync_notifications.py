import unittest
from unittest.mock import patch

import db
import run_hour
from tdtu.snapshot import FetchResult, PortalSnapshot
from user_sync import SyncResult, _diff_summary, sync_one_user


class UserSyncNotificationTests(unittest.TestCase):
    def test_morning_job_fails_when_a_user_sync_fails(self) -> None:
        user = db.User(telegram_id=123, mssv="123", encrypted_pass="encrypted")
        with patch.object(run_hour, "_load_dotenv"), patch.object(db, "get_all_active_users", return_value=[user]), patch.object(db, "log_sync"), patch("user_sync.sync_one_user", return_value=SyncResult(error="portal unavailable")):
            with self.assertRaisesRegex(RuntimeError, "1 user"):
                run_hour.run_morning_sync()

    def test_failed_schedule_does_not_save_snapshot(self) -> None:
        user = db.User(telegram_id=123, mssv="123", encrypted_pass="encrypted", google_refresh_token="token", google_calendar_id="calendar")
        snapshot = PortalSnapshot(schedule=FetchResult(success=False, data=None, error="portal unavailable"))
        with patch("crypto.decrypt", return_value="password"), patch("tdtu.fetch_portal_snapshot", return_value=snapshot), patch.object(db, "save_snapshot") as save:
            result = sync_one_user(user)
        self.assertIn("portal unavailable", result.error)
        save.assert_not_called()

    def test_missing_calendar_is_reported(self) -> None:
        user = db.User(telegram_id=123, mssv="123", encrypted_pass="encrypted")
        self.assertIn("Google Calendar", sync_one_user(user).error)

    def test_new_absence_is_reported_with_details(self) -> None:
        old = {
            "schedule": [
                {
                    "subject_name": "Lập trình Web",
                    "session_date": "2026-09-29",
                    "start_time": "14:25:00",
                    "end_time": "17:05:00",
                    "room": "B202",
                    "status": "scheduled",
                }
            ]
        }
        new = [
            {
                "subject_name": "Lập trình Web",
                "session_date": "2026-09-29",
                "start_time": "14:25:00",
                "end_time": "17:05:00",
                "room": "B202",
                "status": "absent",
            }
        ]

        summary = _diff_summary(old, new, [])

        self.assertIn("- Báo vắng: 1 tiết", summary)
        self.assertIn("Lập trình Web", summary)
        self.assertIn("29/09/2026", summary)
        self.assertIn("GV báo vắng", summary)

    def test_same_absence_is_not_reported_as_new(self) -> None:
        schedule = [
            {
                "subject_name": "Lập trình Web",
                "session_date": "2026-09-29",
                "start_time": "14:25:00",
                "room": "B202",
                "status": "absent",
            }
        ]

        summary = _diff_summary({"schedule": schedule}, schedule, [])

        self.assertNotIn("Báo vắng", summary)
        self.assertIn("Có thay đổi trong lịch", summary)


if __name__ == "__main__":
    unittest.main()
