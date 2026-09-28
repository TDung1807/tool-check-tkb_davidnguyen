"""user_sync.py – Per-user crawl + change detection.

Orchestrates the crawl-and-sync cycle for a single user:
1. Decrypt credentials
2. Crawl TDTU portal
3. Compare with previous snapshot (hash-based change detection)
4. If changed → sync Google Calendar + save new snapshot
5. Return a result indicating whether changes were found

Usage::

    from user_sync import sync_one_user
    from db import get_all_active_users

    for user in get_all_active_users():
        result = sync_one_user(user)
        if result.has_changes:
            notify(user.telegram_id, result.changes_summary)
"""

from __future__ import annotations

import hashlib
import json
import logging
from dataclasses import dataclass, field

import crypto
import db
from db import User

logger = logging.getLogger(__name__)


@dataclass
class SyncResult:
    """Outcome of a single-user sync cycle."""

    has_changes: bool = False
    changes_summary: str | None = None
    schedule_count: int = 0
    exam_count: int = 0
    deadline_count: int = 0
    error: str | None = None


def hash_schedule_data(
    schedule: list[dict] | None,
    exams: list[dict] | None,
    deadlines: list[dict] | None = None,
) -> str:
    """Produce a deterministic SHA-256 hash of crawled data.

    If the hash matches the previous run → no changes occurred.
    """
    blob = json.dumps(
        {
            "schedule": schedule,
            "exams": exams,
            "deadlines": deadlines,
        },
        sort_keys=True,
        default=str,
    )
    return hashlib.sha256(blob.encode("utf-8")).hexdigest()


def _parse_snapshot_data(old_data: dict | str | None) -> dict:
    if not old_data:
        return {}
    try:
        parsed = json.loads(old_data) if isinstance(old_data, str) else old_data
        return parsed if isinstance(parsed, dict) else {}
    except (json.JSONDecodeError, TypeError):
        return {}


def _schedule_key(item: dict) -> tuple[str, ...]:
    """Return a status-independent identity for one timetable session."""
    return (
        str(item.get("session_date") or item.get("date") or "").strip(),
        str(item.get("day_of_week") or "").strip().lower(),
        str(item.get("start_period") or "").strip(),
        str(item.get("end_period") or "").strip(),
        str(item.get("start_time") or "").strip(),
        str(item.get("subject_name") or item.get("subject") or "").strip().lower(),
        str(item.get("room") or "").strip().lower(),
    )


def _schedule_identity(item: dict) -> tuple[str, ...]:
    """Identify a class while allowing its room/status/time to change."""
    return (
        str(item.get("session_date") or item.get("date") or "").strip(),
        str(item.get("subject_name") or item.get("subject") or "").strip().lower(),
        str(item.get("start_period") or item.get("start_time") or "").strip(),
        str(item.get("end_period") or item.get("end_time") or "").strip(),
    )


def _format_schedule_detail(item: dict) -> str:
    subject = str(item.get("subject_name") or item.get("subject") or "Môn học").strip()
    date = str(item.get("session_date") or item.get("date") or "").strip()
    try:
        date = __import__("datetime").date.fromisoformat(date).strftime("%d/%m/%Y")
    except ValueError:
        date = date or "chưa rõ ngày"
    start = str(item.get("start_time") or "").strip()[:5]
    end = str(item.get("end_time") or "").strip()[:5]
    if start and end:
        time_text = f"{start}–{end}"
    else:
        time_text = "chưa rõ giờ"
    room = str(item.get("room") or "").strip() or "chưa rõ phòng"
    status = str(item.get("status") or "scheduled").strip().lower()
    status_text = {
        "scheduled": "học bình thường",
        "absent": "báo vắng",
        "cancelled": "đã hủy",
        "makeup": "học bù",
        "moved": "đã chuyển lịch",
    }.get(status, status)
    return f"{subject} — {date} — {time_text} — phòng {room} — {status_text}"


def _format_absence_detail(item: dict) -> str:
    subject = str(item.get("subject_name") or item.get("subject") or "Môn học").strip()
    date = str(item.get("session_date") or item.get("date") or "").strip()
    if date:
        try:
            date = __import__("datetime").date.fromisoformat(date).strftime("%d/%m/%Y")
        except ValueError:
            pass
    day = str(item.get("day_of_week") or "").strip()
    when = date or day or "chưa rõ ngày"
    start = str(item.get("start_time") or "").strip()
    end = str(item.get("end_time") or "").strip()
    if start and end:
        when += f", {start[:5]}–{end[:5]}"
    elif start:
        when += f", {start[:5]}"
    room = str(item.get("room") or "").strip()
    if room:
        when += f", phòng {room}"
    return f"{subject} — {when} — GV báo vắng"


def _diff_summary(
    old_data: dict | None,
    new_schedule: list[dict] | None,
    new_exams: list[dict] | None,
) -> str:
    """Build a brief Vietnamese summary of what changed."""
    parts: list[str] = []

    old_parsed = _parse_snapshot_data(old_data)
    old_schedule = old_parsed.get("schedule") or []
    old_exams = old_parsed.get("exams") or []
    current_schedule = new_schedule or []
    current_exams = new_exams or []

    old_schedule_by_key = {_schedule_identity(item): item for item in old_schedule if isinstance(item, dict)}
    new_schedule_by_key = {_schedule_identity(item): item for item in current_schedule if isinstance(item, dict)}
    added_keys = set(new_schedule_by_key) - set(old_schedule_by_key)
    removed_keys = set(old_schedule_by_key) - set(new_schedule_by_key)
    if added_keys:
        parts.append(f"- Thêm môn/tiết: {len(added_keys)}")
        parts.extend(f"  - {_format_schedule_detail(new_schedule_by_key[key])}" for key in sorted(added_keys))
    if removed_keys:
        parts.append(f"- Xóa môn/tiết: {len(removed_keys)}")
        parts.extend(f"  - {_format_schedule_detail(old_schedule_by_key[key])}" for key in sorted(removed_keys))

    modified: list[str] = []
    for key in sorted(set(old_schedule_by_key) & set(new_schedule_by_key)):
        old_item = old_schedule_by_key[key]
        new_item = new_schedule_by_key[key]
        changed_fields = []
        for field, label in (("start_time", "giờ học"), ("end_time", "giờ kết thúc"), ("room", "phòng"), ("status", "trạng thái")):
            if str(old_item.get(field) or "").strip().lower() != str(new_item.get(field) or "").strip().lower():
                changed_fields.append(label)
        if changed_fields:
            modified.append(
                f"   Từ  -->  {_format_schedule_detail(old_item)}\n"
                f"   Thành  -->  {_format_schedule_detail(new_item)}"
            )
    if modified:
        parts.append("- Cập nhật môn/tiết:")
        parts.extend(modified)

    newly_absent = [
        item
        for key, item in new_schedule_by_key.items()
        if str(item.get("status") or "scheduled").lower() == "absent"
        and str(old_schedule_by_key.get(key, {}).get("status") or "scheduled").lower() != "absent"
    ]
    if newly_absent:
        parts.append(f"- Báo vắng: {len(newly_absent)} tiết")
        parts.append("")
        parts.append("Chi tiết báo vắng:")
        parts.extend(f"- {_format_absence_detail(item)}" for item in newly_absent)

    if not parts and current_schedule != old_schedule:
        parts.append("- Thời khóa biểu có thay đổi")

    old_exam_keys = {json.dumps(item, sort_keys=True, default=str) for item in old_exams}
    new_exam_keys = {json.dumps(item, sort_keys=True, default=str) for item in current_exams}
    if len(new_exam_keys - old_exam_keys):
        parts.append(f"- Thêm: {len(new_exam_keys - old_exam_keys)} lịch thi")
    if len(old_exam_keys - new_exam_keys):
        parts.append(f"- Xóa: {len(old_exam_keys - new_exam_keys)} lịch thi")

    return "\n".join(parts) if parts else "- Có thay đổi trong lịch"


def sync_one_user(user: User) -> SyncResult:
    """Run the full crawl-compare-sync cycle for one user.

    Returns a :class:`SyncResult` with ``has_changes=True`` when the
    schedule/exam data differs from the stored snapshot.
    """
    logger.info("Syncing user %s (MSSV=%s)…", user.telegram_id, user.mssv)

    # 1. Decrypt credentials
    try:
        password = crypto.decrypt(user.encrypted_pass)
    except crypto.DecryptionError as exc:
        logger.error("Cannot decrypt password for user %s: %s", user.telegram_id, exc)
        return SyncResult(error=f"Lỗi giải mã mật khẩu: {exc}")

    # 2. Crawl TDTU portal
    try:
        from tdtu import fetch_portal_snapshot

        snapshot = fetch_portal_snapshot(user.mssv, password, weeks_ahead=3)
    except Exception as exc:
        logger.exception("Crawl failed for user %s", user.telegram_id)
        return SyncResult(error=f"Lỗi crawl TDTU: {exc}")

    schedule = snapshot.schedule.data if snapshot.schedule.success else None
    exams = snapshot.exams.data if snapshot.exams.success else None

    # 3. eLearning deadlines (best-effort)
    elearning_deadlines = None
    deadline_window = None
    try:
        from elearning import PlaywrightElearningCrawler

        elearning_crawler = PlaywrightElearningCrawler()
        crawl_res = elearning_crawler.crawl_deadlines(user.mssv, password)
        elearning_deadlines = crawl_res.items
        deadline_window = (crawl_res.window_start, crawl_res.window_end)
    except Exception:
        logger.debug("eLearning crawl skipped for user %s", user.telegram_id)

    # 4. Change detection
    new_hash = hash_schedule_data(schedule, exams, elearning_deadlines)
    old_snapshot = db.get_snapshot(user.telegram_id)
    old_hash = old_snapshot.get("schedule_hash") if old_snapshot else None
    old_data = old_snapshot.get("schedule_data") if old_snapshot else None

    if old_hash and old_hash == new_hash:
        logger.info("No changes for user %s.", user.telegram_id)
        return SyncResult(
            has_changes=False,
            schedule_count=len(schedule or []),
            exam_count=len(exams or []),
            deadline_count=len(elearning_deadlines or []),
        )

    # 5. Changes detected → sync Google Calendar
    logger.info("Changes detected for user %s – syncing Calendar.", user.telegram_id)

    if user.google_refresh_token and user.google_calendar_id:
        try:
            from calendar_sync import sync_crawled_data_to_google_calendar
            from google_oauth import get_calendar_service

            cal_service = get_calendar_service(user.google_refresh_token)

            sync_crawled_data_to_google_calendar(
                schedule,
                exams,
                student_id=user.mssv,
                deadlines=elearning_deadlines,
                deadline_window=deadline_window,
                calendar_service=cal_service,
                calendar_id=user.google_calendar_id,
            )
        except Exception as exc:
            logger.exception("Calendar sync failed for user %s", user.telegram_id)
            return SyncResult(error=f"Lỗi sync Calendar: {exc}")
    else:
        logger.warning("User %s has no Google Calendar configured.", user.telegram_id)

    # 6. Save new snapshot
    snapshot_data = json.dumps(
        {"schedule": schedule, "exams": exams, "deadlines": elearning_deadlines},
        default=str,
    )
    db.save_snapshot(user.telegram_id, new_hash, snapshot_data)
    db.update_last_sync(user.telegram_id)

    changes_summary = _diff_summary(old_data, schedule, exams)

    return SyncResult(
        has_changes=True,
        changes_summary=changes_summary,
        schedule_count=len(schedule or []),
        exam_count=len(exams or []),
        deadline_count=len(elearning_deadlines or []),
    )
