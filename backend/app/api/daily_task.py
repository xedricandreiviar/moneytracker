"""API endpoints for daily task and streak management.

Provides:
- GET /api/daily-task — current task with hours remaining
- POST /api/daily-task/complete — mark as "no transactions"
- GET /api/streak — current streak info

Requirements covered: 1.1, 1.2, 1.3, 1.4, 1.5, 1.6
"""

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.database import get_db
from app.models.user import User
from app.schemas.daily_task import (
    DailyTaskCompleteResponse,
    DailyTaskResponse,
    StreakResponse,
)
from app.services.daily_task_service import (
    DailyTaskError,
    check_grace_period,
    complete_task,
    get_current_task,
)
from app.services.streak_service import get_current_streak

router = APIRouter(prefix="/api", tags=["daily-task"])


def _get_current_user(db: Session = Depends(get_db)) -> User:
    """Get or create the current user.

    In a real app this would use authentication. For now, we use user_id=1.
    """
    user = db.query(User).filter(User.id == 1).first()
    if not user:
        user = User(id=1, timezone="UTC")
        db.add(user)
        db.commit()
        db.refresh(user)
    return user


@router.get("/daily-task", response_model=DailyTaskResponse)
def get_daily_task_endpoint(
    user: User = Depends(_get_current_user),
    db: Session = Depends(get_db),
) -> DailyTaskResponse:
    """Get the current daily task with hours remaining.

    Returns 404 if no task exists for today.
    Requirement 1.2: Display hours remaining when task is incomplete.
    """
    task_info = get_current_task(db=db, user_id=user.id)

    if task_info is None:
        raise HTTPException(
            status_code=404,
            detail="No daily task found for today.",
        )

    task = task_info.task
    return DailyTaskResponse(
        id=task.id,
        user_id=task.user_id,
        task_date=task.task_date,
        status=task.status.value,
        completion_type=task.completion_type.value if task.completion_type else None,
        completed_at_utc=task.completed_at_utc,
        hours_remaining=round(task_info.hours_remaining, 2),
    )


@router.post("/daily-task/complete", response_model=DailyTaskCompleteResponse)
def complete_daily_task_endpoint(
    user: User = Depends(_get_current_user),
    db: Session = Depends(get_db),
) -> DailyTaskCompleteResponse:
    """Mark the current daily task as 'no transactions'.

    Requirement 1.3: Display "no transactions" option.
    Requirement 1.4: Record task as completed when user selects "no transactions".
    Requirement 1.6: Increment streak on completion.
    """
    task_info = get_current_task(db=db, user_id=user.id)

    if task_info is None:
        raise HTTPException(
            status_code=404,
            detail="No daily task found for today.",
        )

    task = task_info.task

    # Check if already completed
    if task.status.value == "completed":
        raise HTTPException(
            status_code=400,
            detail="Daily task is already completed.",
        )

    # Check if missed (not recoverable here — use grace period endpoint for that)
    if task.status.value == "missed":
        raise HTTPException(
            status_code=400,
            detail="Daily task has been missed and cannot be completed.",
        )

    try:
        completed_task = complete_task(
            db=db,
            task_id=task.id,
            completion_type="no_transactions",
        )
    except DailyTaskError as e:
        raise HTTPException(status_code=400, detail=e.message)

    return DailyTaskCompleteResponse(
        id=completed_task.id,
        user_id=completed_task.user_id,
        task_date=completed_task.task_date,
        status=completed_task.status.value,
        completion_type=completed_task.completion_type.value if completed_task.completion_type else "no_transactions",
        completed_at_utc=completed_task.completed_at_utc,
    )


@router.get("/streak", response_model=StreakResponse)
def get_streak_endpoint(
    user: User = Depends(_get_current_user),
    db: Session = Depends(get_db),
) -> StreakResponse:
    """Get the current streak info including grace period status.

    Requirements 1.6, 2.2, 2.4: Streak count and grace period info.
    """
    current_streak = get_current_streak(db=db, user_id=user.id)
    grace_status = check_grace_period(db=db, user_id=user.id)

    return StreakResponse(
        current_streak=current_streak,
        grace_period_active=grace_status.is_active,
        grace_remaining_hours=round(grace_status.remaining_hours, 2),
        grace_remaining_minutes=round(grace_status.remaining_minutes, 2),
    )
