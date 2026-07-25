"""APScheduler job for daily task generation.

Runs every 60 seconds. For each user whose local midnight has passed
without a task for the new day, generates a pending Daily_Task.

Requirement 1.1: Generate a new Daily_Task within 60 seconds of midnight.
"""

import logging
from datetime import datetime, timezone

from app.database import SessionLocal
from app.models.user import User
from app.services.daily_task_service import _get_user_local_today, generate_daily_task

logger = logging.getLogger(__name__)


def generate_daily_tasks_job() -> None:
    """Check all users and generate daily tasks for those whose midnight has passed.

    This job:
    1. Opens a new database session (independent of request lifecycle).
    2. Queries all users.
    3. For each user, computes their local "today" based on timezone.
    4. If no task exists for today, generates one.
    5. Commits and closes the session.
    """
    db = SessionLocal()
    try:
        now_utc = datetime.now(timezone.utc)
        users = db.query(User).all()

        tasks_created = 0
        for user in users:
            today = _get_user_local_today(user, now_utc)

            # generate_daily_task is idempotent — it won't create duplicates
            from app.models.daily_task import DailyTask

            existing = (
                db.query(DailyTask)
                .filter(DailyTask.user_id == user.id, DailyTask.task_date == today)
                .first()
            )

            if existing is None:
                generate_daily_task(
                    db=db,
                    user_id=user.id,
                    task_date=today,
                    now_utc=now_utc,
                )
                tasks_created += 1

        if tasks_created > 0:
            logger.info(f"Daily task job: created {tasks_created} task(s).")
    except Exception:
        logger.exception("Error in daily task generation job")
    finally:
        db.close()
