"""APScheduler job for daily task reminder notifications.

Runs every 60 seconds. For each user whose configured reminder time
(default 8 PM local) has passed and daily task is still incomplete,
sends a reminder notification (at most once per day).

Requirement 12.2: Send reminder when user hasn't completed daily task
by configured time (default 8 PM local), at most once per day.
"""

import logging
from datetime import datetime, time, timezone

from app.database import SessionLocal
from app.models.user import User
from app.services.daily_task_service import _get_user_local_today
from app.services.notification_service import send_daily_reminder

logger = logging.getLogger(__name__)

# Default reminder time: 8 PM (20:00) local time
DEFAULT_REMINDER_HOUR = 20
DEFAULT_REMINDER_MINUTE = 0


def daily_reminder_job() -> None:
    """Check all users and send daily task reminders where appropriate.

    This job:
    1. Opens a new database session (independent of request lifecycle).
    2. Queries all users.
    3. For each user, computes their local time.
    4. If local time has passed the reminder hour (default 8 PM) and
       the daily task is incomplete, sends a reminder (at most once per day).
    5. Commits and closes the session.

    The at-most-once guarantee is enforced inside send_daily_reminder().
    """
    db = SessionLocal()
    try:
        now_utc = datetime.now(timezone.utc)
        users = db.query(User).all()

        reminders_sent = 0
        for user in users:
            try:
                # Get user's local "today" and current local time
                today = _get_user_local_today(user, now_utc)

                # Determine user's current local time
                import pytz

                try:
                    user_tz = pytz.timezone(user.timezone)
                except pytz.exceptions.UnknownTimeZoneError:
                    user_tz = pytz.UTC

                local_now = now_utc.astimezone(user_tz)
                reminder_time = time(DEFAULT_REMINDER_HOUR, DEFAULT_REMINDER_MINUTE)

                # Only send reminder if current local time >= reminder time
                if local_now.time() >= reminder_time:
                    result = send_daily_reminder(
                        db=db,
                        user_id=user.id,
                        task_date=today,
                    )
                    if result is not None:
                        reminders_sent += 1

            except Exception:
                logger.exception(
                    f"Error sending daily reminder for user {user.id}"
                )
                continue

        db.commit()

        if reminders_sent > 0:
            logger.info(
                f"Daily reminder job: sent {reminders_sent} reminder(s)."
            )
    except Exception:
        logger.exception("Error in daily reminder job")
        db.rollback()
    finally:
        db.close()
