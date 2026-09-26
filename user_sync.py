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


def _diff_summary(
    old_data: dict | None,
    new_schedule: list[dict] | None,
    new_exams: list[dict] | None,
) -> str:
    """Build a brief Vietnamese summary of what changed."""
    parts: list[str] = []

    old_schedule_count = 0
    old_exam_count = 0
    if old_data:
        try:
            old_parsed = json.loads(old_data) if isinstance(old_data, str) else old_data
            old_schedule_count = len(old_parsed.get("schedule") or [])
            old_exam_count = len(old_parsed.get("exams") or [])
        except (json.JSONDecodeError, TypeError, AttributeError):
            pass

    new_schedule_count = len(new_schedule or [])
    new_exam_count = len(new_exams or [])

    if new_schedule_count != old_schedule_count:
        diff = new_schedule_count - old_schedule_count
        if diff > 0:
            parts.append(f"+{diff} lịch học mới")
        else:
            parts.append(f"{diff} lịch học bị xóa")
    elif new_schedule_count > 0:
        parts.append("Lịch học có thay đổi")

    if new_exam_count != old_exam_count:
        diff = new_exam_count - old_exam_count
        if diff > 0:
            parts.append(f"+{diff} lịch thi mới")
        else:
            parts.append(f"{diff} lịch thi bị xóa")
    elif new_exam_count > 0 and old_exam_count > 0:
        parts.append("Lịch thi có thay đổi")

    return ", ".join(parts) if parts else "Có thay đổi trong lịch"


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
