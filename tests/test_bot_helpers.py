import datetime as dt
import os
import unittest
from unittest.mock import patch

from course_aliases import shorten_course_name
import db
from telegram_mvp_bot import (
    ADD_FORM_SKIP_WHERE_CALLBACK,
    _advance_add_form_state,
    _build_add_appointment_from_form,
    _build_add_form_input_markup,
    _build_add_form_step_keyboard,
    _build_deadline_detail_text,
    _build_deadline_keyboard,
    _build_deadline_list_text,
    _build_exam_list_text,
    _build_today_appointments_text,
    _deadline_callback_key,
    _format_deadline_due,
    _is_add_form_complete,
    _new_add_form_state,
    _parse_add_fields,
    _parse_schedule_day_arg,
    _skip_add_form_optional_step,
)
from webhook_app import (
    MENU_ADD_CALLBACK,
    MENU_DEADLINE_CALLBACK,
    MENU_EXAM_CALLBACK,
    MENU_SCHEDULE_CALLBACK,
    MENU_STATUS_CALLBACK,
    MENU_TODAY_CALLBACK,
    _build_main_menu_keyboard,
    _build_start_message,
    _build_status_text,
)


class BotHelperTests(unittest.TestCase):
    def test_today_text_includes_class_and_appointment_rows(self) -> None:
        with patch("telegram_mvp_bot.local_today", return_value=dt.date(2026, 9, 29)):
            text = _build_today_appointments_text(
                [
                    {"subject_name": "Lập trình Web", "start_time": "08:30", "room": "C204"},
                    {"title": "Họp nhóm", "start_time": "14:00", "location": "B402"},
                ]
            )

        self.assertIn("Lập trình Web", text)
        self.assertIn("Họp nhóm", text)
        self.assertLess(text.index("Lập trình Web"), text.index("Họp nhóm"))

    def test_main_menu_exposes_primary_user_actions(self) -> None:
        keyboard = _build_main_menu_keyboard()
        callbacks = {
            button["callback_data"]
            for row in keyboard["inline_keyboard"]
            for button in row
        }

        self.assertEqual(
            callbacks,
            {
                MENU_TODAY_CALLBACK,
                MENU_SCHEDULE_CALLBACK,
                MENU_DEADLINE_CALLBACK,
                MENU_EXAM_CALLBACK,
                MENU_ADD_CALLBACK,
                MENU_STATUS_CALLBACK,
            },
        )

    def test_status_text_reports_configuration_without_secret_values(self) -> None:
        with patch.dict(
            os.environ,
            {
                "STUDENT_ID": "student-123",
                "PASSWORD": "super-secret-password",
                "GOOGLE_CALENDAR_ID": "calendar@example.test",
                "GOOGLE_SERVICE_ACCOUNT_JSON": '{"private_key":"private-secret"}',
                "GEMINI_API_KEY": "",
            },
            clear=False,
        ):
            status = _build_status_text(
                db.User(
                    telegram_id=123,
                    mssv="student-123",
                    encrypted_pass="encrypted-password",
                    google_refresh_token="encrypted-refresh-token",
                    google_calendar_id="calendar@example.test",
                )
            )

        self.assertIn("TDTU: Đã kết nối", status)
        self.assertIn("Google Calendar: Đã kết nối", status)
        self.assertIn("Smart Paste (AI): Chưa kết nối", status)
        self.assertNotIn("super-secret-password", status)
        self.assertNotIn("private-secret", status)

    def test_start_message_includes_connection_status_for_new_user(self) -> None:
        message = _build_start_message(None)

        self.assertIn("TDTU: Chưa kết nối", message)
        self.assertIn("Google Calendar: Chưa kết nối", message)
        self.assertIn("Bắt đầu kết nối", message)

    def test_start_message_includes_ready_status_for_connected_user(self) -> None:
        user = db.User(
            telegram_id=123,
            mssv="student-123",
            encrypted_pass="encrypted-password",
            google_refresh_token="encrypted-refresh-token",
            google_calendar_id="calendar@example.test",
        )

        message = _build_start_message(user)

        self.assertIn("TDTU: Đã kết nối", message)
        self.assertIn("Google Calendar: Đã kết nối", message)

    def test_course_name_manual_alias_overrides_auto_shortening(self) -> None:
        aliases = {"Lập trình hướng đối tượng": "OOP"}

        self.assertEqual(shorten_course_name("Lập trình hướng đối tượng", aliases), "OOP")

    def test_course_name_auto_removes_leading_code(self) -> None:
        self.assertEqual(
            shorten_course_name("503071 - Lập trình Web nâng cao - Nhóm 01"),
            "Lập trình Web nâng cao",
        )

    def test_course_name_auto_removes_moodle_prefix_but_keeps_group_suffix(self) -> None:
        self.assertEqual(
            shorten_course_name("HK2_2025_501032_Đại số tuyến tính cho Công nghệ thông tin_N02"),
            "Đại số tuyến tính cho Công nghệ thông tin_N02",
        )

    def test_format_deadline_due_uses_vietnam_local_time(self) -> None:
        self.assertEqual(_format_deadline_due("2026-05-20T00:00:00+07:00"), "20/05/2026 00:00")
        self.assertEqual(_format_deadline_due("2026-05-19T17:00:00+00:00"), "20/05/2026 00:00")

    def test_deadline_text_includes_progress_when_present(self) -> None:
        rows = [
            {
                "course_id": "501032",
                "course_name": "HK2_2025_501032_Đại số tuyến tính cho Công nghệ thông tin_N02",
                "activity_name": "Bài tập cuối kỳ",
                "due_date": "2026-05-20T00:00:00+07:00",
                "progress_percent": 75,
                "lessons_completed": 15,
                "lessons_total": 20,
            }
        ]

        list_text = _build_deadline_list_text(rows)
        detail_text = _build_deadline_detail_text(rows[0])

        self.assertIn("Đại số tuyến tính cho Công nghệ thông tin_N02", list_text)
        self.assertIn("75%", list_text)
        self.assertIn("Tiến độ: 75% (15/20 bài)", detail_text)

    def test_deadline_callback_key_is_unique_per_deadline_activity(self) -> None:
        row_a = {
            "course_id": "501032",
            "activity_name": "Bài tập 1",
            "activity_url": "https://example.test/mod/assign/view.php?id=11",
            "due_date": "2026-05-20T00:00:00+07:00",
        }
        row_b = {
            "course_id": "501032",
            "activity_name": "Bài tập 2",
            "activity_url": "https://example.test/mod/quiz/view.php?id=22",
            "due_date": "2026-05-21T00:00:00+07:00",
        }

        self.assertNotEqual(_deadline_callback_key(row_a), _deadline_callback_key(row_b))

    def test_deadline_keyboard_uses_distinct_callback_data_for_same_course(self) -> None:
        rows = [
            {
                "course_id": "501032",
                "course_name": "HK2_2025_501032_Đại số tuyến tính cho Công nghệ thông tin_N02",
                "activity_name": "Bài tập 1",
                "activity_url": "https://example.test/mod/assign/view.php?id=11",
                "due_date": "2026-05-20T00:00:00+07:00",
            },
            {
                "course_id": "501032",
                "course_name": "HK2_2025_501032_Đại số tuyến tính cho Công nghệ thông tin_N02",
                "activity_name": "Bài tập 2",
                "activity_url": "https://example.test/mod/quiz/view.php?id=22",
                "due_date": "2026-05-21T00:00:00+07:00",
            },
        ]

        keyboard = _build_deadline_keyboard(rows)
        callbacks = [btn[0]["callback_data"] for btn in keyboard["inline_keyboard"]]

        self.assertEqual(len(callbacks), 2)
        self.assertEqual(len(set(callbacks)), 2)

    def test_exam_text_formats_tagged_calendar_events(self) -> None:
        text = _build_exam_list_text(
            [
                {
                    "title": "[EXAM] Cuoi ky - Operating Systems",
                    "start": "2026-05-21T08:00:00+07:00",
                    "location": "A101",
                }
            ]
        )

        self.assertIn("21/05/2026 08:00", text)
        self.assertIn("Cuoi ky - Operating Systems", text)
        self.assertIn("@ A101", text)

    def test_parse_schedule_day_arg_supports_vietnamese_relative_and_weekday(self) -> None:
        today = dt.date(2026, 5, 13)

        self.assertEqual(_parse_schedule_day_arg("mai", today=today), dt.date(2026, 5, 14))
        self.assertEqual(_parse_schedule_day_arg("thứ 2", today=today), dt.date(2026, 5, 18))
        self.assertEqual(_parse_schedule_day_arg("20/05", today=today), dt.date(2026, 5, 20))

    def test_parse_add_fields_accepts_missing_values_but_rejects_all_blank(self) -> None:
        parsed = _parse_add_fields("Ngày: 16/5\nGiờ: 9h00\nLàm gì: Họp nhóm\nỞ đâu: B402")

        self.assertEqual(parsed, {"date": "16/5", "time": "9h00", "job": "Họp nhóm", "where": "B402"})
        with self.assertRaises(ValueError):
            _parse_add_fields("Ngày: \nGiờ: 9h00\nLàm gì: Họp nhóm\nỞ đâu: ")

    def test_add_form_state_collects_values_step_by_step_and_builds_payload(self) -> None:
        state = _new_add_form_state()
        self.assertEqual(state["step"], "date")

        self.assertIn("16/5", _build_add_form_input_markup(state)["input_field_placeholder"])
        _advance_add_form_state(state, "16/5")
        self.assertEqual(state["step"], "time")
        self.assertIn("9h00", _build_add_form_input_markup(state)["input_field_placeholder"])

        _advance_add_form_state(state, "9h00")
        self.assertEqual(state["step"], "job")

        review_prompt = _advance_add_form_state(state, "Họp nhóm")
        self.assertEqual(state["step"], "where")
        self.assertIn("địa điểm", review_prompt.lower())
        step_keyboard = _build_add_form_step_keyboard(state)
        self.assertEqual(step_keyboard["inline_keyboard"][0][0]["callback_data"], ADD_FORM_SKIP_WHERE_CALLBACK)

        review = _skip_add_form_optional_step(state)
        self.assertTrue(_is_add_form_complete(state))
        self.assertEqual(state["date"], "16/5")
        self.assertEqual(state["time"], "9h00")
        self.assertIsNone(state["where"])
        self.assertIn("Done", review)
        title, appointment_date, start_time, location = _build_add_appointment_from_form(state)

        self.assertEqual(title, "Họp nhóm")
        self.assertEqual(appointment_date, dt.date(dt.date.today().year, 5, 16))
        self.assertEqual(start_time, "09:00:00")
        self.assertIsNone(location)

    def test_add_form_time_rejects_colon_separator(self) -> None:
        state = _new_add_form_state()
        _advance_add_form_state(state, "16/5")

        with self.assertRaises(ValueError):
            _advance_add_form_state(state, "9:00")


if __name__ == "__main__":
    unittest.main()
