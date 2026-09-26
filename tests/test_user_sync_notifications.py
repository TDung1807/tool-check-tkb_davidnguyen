import unittest

from user_sync import _diff_summary


class UserSyncNotificationTests(unittest.TestCase):
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
