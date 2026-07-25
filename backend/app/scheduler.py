"""APScheduler integration with FastAPI lifespan."""

from apscheduler.schedulers.background import BackgroundScheduler

from app.config import settings

scheduler = BackgroundScheduler(
    job_defaults={
        "coalesce": True,
        "max_instances": 1,
        "misfire_grace_time": 60,
    }
)


def _register_jobs() -> None:
    """Register all scheduled jobs with the scheduler."""
    from app.jobs.daily_reminder_job import daily_reminder_job
    from app.jobs.daily_task_job import generate_daily_tasks_job
    from app.jobs.insight_jobs import (
        monthly_summary_job,
        spike_detection_job,
        weekly_summary_job,
    )

    # Requirement 1.1: Generate daily tasks within 60 seconds of midnight.
    # Runs every 60 seconds to check all users.
    scheduler.add_job(
        generate_daily_tasks_job,
        trigger="interval",
        seconds=60,
        id="generate_daily_tasks",
        replace_existing=True,
    )

    # Requirement 5.1: Weekly summary generated at week end.
    # Runs daily at 00:05 to check if a week just ended per user locale.
    scheduler.add_job(
        weekly_summary_job,
        trigger="cron",
        hour=0,
        minute=5,
        id="weekly_summary",
        replace_existing=True,
    )

    # Requirement 5.2: Monthly summary at month end.
    # Runs daily at 00:10, job itself only executes on the 1st of each month.
    scheduler.add_job(
        monthly_summary_job,
        trigger="cron",
        hour=0,
        minute=10,
        id="monthly_summary",
        replace_existing=True,
    )

    # Requirement 6.1: Spending spike detection daily.
    # Runs every day at 00:15 to detect spending anomalies.
    scheduler.add_job(
        spike_detection_job,
        trigger="cron",
        hour=0,
        minute=15,
        id="spike_detection",
        replace_existing=True,
    )

    # Requirement 12.2: Daily task reminder at user-configured time (default 8 PM).
    # Runs every 60 seconds to check all users and send at-most-one reminder per day.
    scheduler.add_job(
        daily_reminder_job,
        trigger="interval",
        seconds=60,
        id="daily_reminder",
        replace_existing=True,
    )


def start_scheduler() -> None:
    """Start the APScheduler background scheduler.

    Registers all jobs and starts the scheduler.
    """
    if settings.scheduler_enabled and not scheduler.running:
        _register_jobs()
        scheduler.start()


def shutdown_scheduler() -> None:
    """Gracefully shut down the scheduler."""
    if scheduler.running:
        scheduler.shutdown(wait=False)
