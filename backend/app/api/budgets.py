"""API endpoints for budget management.

Provides GET, POST, PUT, DELETE for /api/budgets.
"""

from datetime import date

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import JSONResponse
from sqlalchemy.orm import Session

from app.database import get_db
from app.models.user import User
from app.models.user_locale import UserLocale
from app.schemas.budget import (
    BudgetCreateRequest,
    BudgetListResponse,
    BudgetPeriodResponse,
    BudgetProjectionResponse,
    BudgetResponse,
    BudgetUpdateRequest,
)
from app.services.budget_service import (
    BudgetConflictError,
    BudgetValidationError,
    calculate_budget_projection,
    create_budget,
    deactivate_budget,
    get_active_period_record,
    get_user_budgets,
    update_budget_limit,
)
from app.services.locale_service import LOCALE_CONFIGS, LocaleConfig

router = APIRouter(prefix="/api/budgets", tags=["budgets"])


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


def _get_user_locale(db: Session, user_id: int) -> LocaleConfig:
    """Get the user's locale config from their UserLocale record.

    Falls back to US locale if no UserLocale record exists.
    """
    user_locale = (
        db.query(UserLocale).filter(UserLocale.user_id == user_id).first()
    )
    if user_locale:
        country_code = user_locale.country_code
        locale = LOCALE_CONFIGS.get(country_code)
        if locale:
            return locale
    # Default fallback
    return LOCALE_CONFIGS["US"]


def _get_user_decimal_precision(db: Session, user_id: int) -> int:
    """Get decimal precision from the user's locale config."""
    user_locale = (
        db.query(UserLocale).filter(UserLocale.user_id == user_id).first()
    )
    if user_locale:
        return user_locale.decimal_precision
    return 2  # Default USD precision


def _budget_to_response(budget, db: Session) -> BudgetResponse:
    """Convert a Budget model instance to a BudgetResponse schema with projection."""
    # Get current period record
    period = get_active_period_record(db, budget.id)

    current_period = None
    projection = None

    if period:
        current_period = BudgetPeriodResponse(
            period_start=period.period_start,
            period_end=period.period_end,
            spent_smallest_unit=period.spent_smallest_unit,
            status=period.status.value if hasattr(period.status, "value") else period.status,
        )

        # Calculate projection
        proj = calculate_budget_projection(budget, period, today=date.today())
        projection = BudgetProjectionResponse(
            remaining=proj.remaining,
            projected_spend=proj.projected_spend,
            status=proj.status,
            overage=proj.overage,
        )

    return BudgetResponse(
        id=budget.id,
        user_id=budget.user_id,
        category_id=budget.category_id,
        period_type=budget.period_type.value if hasattr(budget.period_type, "value") else budget.period_type,
        limit_smallest_unit=budget.limit_smallest_unit,
        currency_code=budget.currency_code,
        is_active=budget.is_active,
        created_at_utc=budget.created_at_utc,
        current_period=current_period,
        projection=projection,
    )


@router.get("", response_model=BudgetListResponse)
def list_budgets_endpoint(
    user: User = Depends(_get_current_user),
    db: Session = Depends(get_db),
) -> BudgetListResponse:
    """List active budgets with current status and projection.

    Returns each budget with its current period record and projection
    (remaining, status, projected_spend, overage).
    """
    budgets = get_user_budgets(db=db, user_id=user.id, active_only=True)
    response_items = [_budget_to_response(b, db) for b in budgets]

    return BudgetListResponse(
        budgets=response_items,
        count=len(response_items),
    )


@router.post("", response_model=BudgetResponse, status_code=201)
def create_budget_endpoint(
    request: BudgetCreateRequest,
    user: User = Depends(_get_current_user),
    db: Session = Depends(get_db),
) -> BudgetResponse | JSONResponse:
    """Create a new budget.

    Validates input, checks for duplicates, and returns the new budget.
    Returns 422 on invalid limit, 409 on duplicate active budget.
    """
    locale = _get_user_locale(db, user.id)
    decimal_precision = _get_user_decimal_precision(db, user.id)

    try:
        budget = create_budget(
            db=db,
            user_id=user.id,
            period_type=request.period_type,
            limit_smallest_unit=request.limit_smallest_unit,
            currency_code=request.currency_code,
            decimal_precision=decimal_precision,
            category_id=request.category_id,
            locale=locale,
            reference_date=date.today(),
        )
    except BudgetValidationError as e:
        return JSONResponse(
            status_code=422,
            content={
                "detail": [{"field": e.field, "message": e.message}],
            },
        )
    except BudgetConflictError as e:
        return JSONResponse(
            status_code=409,
            content={
                "detail": e.message,
            },
        )

    return _budget_to_response(budget, db)


@router.put("/{budget_id}", response_model=BudgetResponse)
def update_budget_endpoint(
    budget_id: int,
    request: BudgetUpdateRequest,
    user: User = Depends(_get_current_user),
    db: Session = Depends(get_db),
) -> BudgetResponse | JSONResponse:
    """Update the spending limit of an existing budget.

    Returns 404 if budget not found, 422 if new limit is invalid.
    """
    decimal_precision = _get_user_decimal_precision(db, user.id)

    try:
        budget = update_budget_limit(
            db=db,
            budget_id=budget_id,
            user_id=user.id,
            new_limit_smallest_unit=request.limit_smallest_unit,
            decimal_precision=decimal_precision,
        )
    except BudgetValidationError as e:
        return JSONResponse(
            status_code=422,
            content={
                "detail": [{"field": e.field, "message": e.message}],
            },
        )

    if budget is None:
        raise HTTPException(status_code=404, detail="Budget not found.")

    return _budget_to_response(budget, db)


@router.delete("/{budget_id}", status_code=200)
def deactivate_budget_endpoint(
    budget_id: int,
    user: User = Depends(_get_current_user),
    db: Session = Depends(get_db),
):
    """Deactivate (soft delete) a budget.

    Returns 404 if budget not found.
    """
    budget = deactivate_budget(db=db, budget_id=budget_id, user_id=user.id)

    if budget is None:
        raise HTTPException(status_code=404, detail="Budget not found.")

    return {"detail": "Budget deactivated.", "id": budget.id}
