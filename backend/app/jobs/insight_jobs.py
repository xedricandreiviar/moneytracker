"""APScheduler jobs for insight generation: weekly summaries, monthly summaries, spike detection.

Jobs:
- Weekly summary generation: runs daily, checks if week ended for each user's locale
- Monthly summary generation: runs daily, checks if month ended
- Daily spike detection: runs once per day

Requirements:
- 5.1: Weekly summary generated at week end
- 5.2: Monthly summary generated at month end
- 5.6: Notify user within 1 hour of summary generation
- 6.1: Spike detection when category > 150% of 4-week rolling average
- 6.3: Notify user within 1 hour of spike detection
"""

import json
import logging
from datetime import date, datetime, timedelta, timezone

from app.database import SessionLocal
from app.models.notification import Notification
from app.models.user import User
from app.services.insight_engine import (
    detect_spending_spikes,
    generate_monthly_summary,
    generate_weekly_summary,
)
from app.services.locale_service import LocaleConfig, get_locale_config, get_week_boundaries

logger = logging.getLogger(__name__)


def _get_user_locale(user: User) -> LocaleConfig:
    """Resolve user's locale configuration, falling back to US."""
    if user.locale and user.locale.country_code:
        return get_locale_config(user.locale.country_code)
    return get_locale_config("US")


def _create_notification(
    db,
    user_id: int,
    notification_type: str,
    title: str,
    body: str,
    payload: dict | None = None,
) -> None:
    """Create an in-app notification for a user.

    Requirements 5.6, 6.3: Notify user within 1 hour of summary/spike generation.
    """
    notification = Notification(
        user_id=user_id,
        notification_type=notification_type,
        title=title,
        body=body,
        payload_json=json.dumps(payload) if payload else None,
        is_read=False,
    )
    db.add(notification)


def weekly_summary_job() -> None:
    """Generate weekly summaries for users whose week just ended.

    Runs daily. For each user, checks if yesterday was the last day of
    their locale's week (i.e., today is the start of a new week).
    If so, generates the weekly summary and creates a notification.

    Requirement 5.1: Weekly summary at week end.
    Requirement 5.6: Notify within 1 hour of generation.
    """
    db = SessionLocal()
    try:
        users = db.query(User).all()
        summaries_generated = 0

        for user in users:
            try:
                locale = _get_user_locale(user)
                today = datetime.now(timezone.utc).date()

                # Check if today is the first day of a new week in user's locale
                week_start, _ = get_week_boundaries(today, locale)

                # If today is the week start, then yesterday was the last day of the prior week
                if week_start == today:
                    # Generate summary for the week that just ended (yesterday's week)
                    yesterday = today - timedelta(days=1)
                    _, prior_week_end = get_week_boundaries(yesterday, locale)

                    summary = generate_weekly_summary(
                        db=db,
                        user_id=user.id,
                        week_end_date=prior_week_end,
                        locale=locale,
                    )

                    # Create in-app notification
                    _create_notification(
                        db=db,
                        user_id=user.id,
                        notification_type="weekly_summary",
                        title="Weekly Spending Summary Available",
                        body=(
                            f"Your weekly summary for "
                            f"{summary.week_start.isoformat()} to "
                            f"{summary.week_end.isoformat()} is ready."
                        ),
                        payload={
                            "week_start": summary.week_start.isoformat(),
                            "week_end": summary.week_end.isoformat(),
                            "total_spent": summary.total_spent,
                            "total_received": summary.total_received,
                            "net": summary.net,
                        },
                    )

                    summaries_generated += 1
            except Exception:
                logger.exception(
                    f"Error generating weekly summary for user {user.id}"
                )
                continue

        db.commit()

        if summaries_generated > 0:
            logger.info(
                f"Weekly summary job: generated {summaries_generated} summary(ies)."
            )
    except Exception:
        logger.exception("Error in weekly summary generation job")
        db.rollback()
    finally:
        db.close()


def monthly_summary_job() -> None:
    """Generate monthly summaries for users at the start of a new month.

    Runs daily. Checks if today is the 1st of the month. If so,
    generates the monthly summary for the previous month and creates
    a notification.

    Requirement 5.2: Monthly summary at month end.
    Requirement 5.6: Notify within 1 hour of generation.
    """
    db = SessionLocal()
    try:
        today = datetime.now(timezone.utc).date()

        # Only run on the 1st of the month (summary for the month that just ended)
        if today.day != 1:
            return

        users = db.query(User).all()
        summaries_generated = 0

        # The previous month
        yesterday = today - timedelta(days=1)
        prev_month = yesterday.month
        prev_year = yesterday.year

        for user in users:
            try:
                locale = _get_user_locale(user)

                summary = generate_monthly_summary(
                    db=db,
                    user_id=user.id,
                    month=prev_month,
                    year=prev_year,
                    locale=locale,
                )

                # Create in-app notification
                _create_notification(
                    db=db,
                    user_id=user.id,
                    notification_type="monthly_summary",
                    title="Monthly Spending Summary Available",
                    body=(
                        f"Your monthly summary for "
                        f"{prev_year}-{prev_month:02d} is ready."
                    ),
                    payload={
                        "month": prev_month,
                        "year": prev_year,
                        "total_spent": summary.total_spent,
                        "total_received": summary.total_received,
                        "net": summary.net,
                    },
                )

                summaries_generated += 1
            except Exception:
                logger.exception(
                    f"Error generating monthly summary for user {user.id}"
                )
                continue

        db.commit()

        if summaries_generated > 0:
            logger.info(
                f"Monthly summary job: generated {summaries_generated} summary(ies)."
            )
    except Exception:
        logger.exception("Error in monthly summary generation job")
        db.rollback()
    finally:
        db.close()


def spike_detection_job() -> None:
    """Run daily spending spike detection for all users.

    For each user, detects spending spikes (categories where current week
    spending > 150% of 4-week rolling average) and creates notifications
    for any newly detected spikes.

    Requirement 6.1: Spike detection flags categories > 150% of 4-week average.
    Requirement 6.3: Notify user within 1 hour of spike detection.
    """
    db = SessionLocal()
    try:
        users = db.query(User).all()
        total_spikes_detected = 0

        for user in users:
            try:
                locale = _get_user_locale(user)

                spikes = detect_spending_spikes(
                    db=db,
                    user_id=user.id,
                    locale=locale,
                )

                for spike in spikes:
                    # Create in-app notification for each spike
                    _create_notification(
                        db=db,
                        user_id=user.id,
                        notification_type="spike_alert",
                        title=f"Spending Spike: {spike.category_name}",
                        body=(
                            f"Your spending in {spike.category_name} this week "
                            f"is significantly higher than your 4-week average."
                        ),
                        payload={
                            "category_name": spike.category_name,
                            "current_total": spike.current_total,
                            "rolling_average": spike.rolling_average,
                            "threshold_percentage": spike.threshold_percentage,
                        },
                    )
                    total_spikes_detected += 1

            except Exception:
                logger.exception(
                    f"Error detecting spikes for user {user.id}"
                )
                continue

        db.commit()

        if total_spikes_detected > 0:
            logger.info(
                f"Spike detection job: detected {total_spikes_detected} spike(s)."
            )
    except Exception:
        logger.exception("Error in spike detection job")
        db.rollback()
    finally:
        db.close()
