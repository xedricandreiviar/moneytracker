"""API endpoints for transaction management.

Provides POST, GET for /api/transactions and GET for
/api/transactions/frequent-categories.
"""

import json
from datetime import date
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import JSONResponse
from sqlalchemy.exc import OperationalError
from sqlalchemy.orm import Session

from app.database import get_db
from app.models.user import User
from app.models.user_locale import UserLocale
from app.schemas.transaction import (
    CategoryOverrideRequest,
    CategoryOverrideResponse,
    CategorySuggestionRequest,
    CategorySuggestionResponse,
    FrequentCategoriesResponse,
    TransactionCreateRequest,
    TransactionListResponse,
    TransactionResponse,
    ValidationErrorDetail,
)
from app.services.transaction_service import (
    TransactionValidationError,
    create_transaction,
    get_frequent_categories,
    get_transactions,
    record_category_override,
    suggest_category,
)
from app.services.daily_task_service import auto_complete_on_transaction

router = APIRouter(prefix="/api/transactions", tags=["transactions"])


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


def _get_user_timezone(db: Session, user_id: int) -> str:
    """Look up the user's configured timezone from their locale or user record."""
    user = db.query(User).filter(User.id == user_id).first()
    return user.timezone if user else "UTC"


def _transaction_to_response(transaction, db: Session) -> TransactionResponse:
    """Convert a Transaction model instance to a TransactionResponse schema."""
    # Resolve category name from category_id
    category_name = None
    if transaction.category_id is not None and transaction.category:
        category_name = transaction.category.name

    # Parse tags from JSON
    tags = None
    if transaction.tags_json:
        tags = json.loads(transaction.tags_json)

    return TransactionResponse(
        id=transaction.id,
        user_id=transaction.user_id,
        amount_smallest_unit=transaction.amount_smallest_unit,
        direction=transaction.direction.value,
        currency_code=transaction.currency_code,
        category_name=category_name,
        note=transaction.note,
        payment_method=transaction.payment_method,
        tags=tags,
        transaction_datetime_utc=transaction.transaction_datetime_utc,
        transaction_date_local=transaction.transaction_date_local,
        created_at_utc=transaction.created_at_utc,
    )


@router.post("", response_model=TransactionResponse, status_code=201)
def create_transaction_endpoint(
    request: TransactionCreateRequest,
    user: User = Depends(_get_current_user),
    db: Session = Depends(get_db),
) -> TransactionResponse:
    """Create a new transaction.

    Validates input, persists transaction, returns confirmation.
    Returns 422 with field-level errors for invalid amounts/fields.
    Returns 503 if database is unavailable after retries.
    """
    user_timezone = _get_user_timezone(db, user.id)

    try:
        transaction = create_transaction(
            db=db,
            user_id=user.id,
            amount_smallest_unit=request.amount_smallest_unit,
            direction=request.direction,
            currency_code=request.currency_code,
            category_name=request.category_name,
            note=request.note,
            payment_method=request.payment_method,
            tags=request.tags,
            user_timezone=user_timezone,
        )
    except TransactionValidationError as e:
        # Return 422 with field-level error details
        error_detail = ValidationErrorDetail(field=e.field, message=e.message)
        return JSONResponse(
            status_code=422,
            content={
                "detail": [error_detail.model_dump()],
            },
        )
    except OperationalError:
        # Database unavailable after all retry attempts
        raise HTTPException(
            status_code=503,
            detail="Service temporarily unavailable. Please try again later.",
            headers={"Retry-After": "5"},
        )

    # Requirement 1.5: Auto-complete daily task when a transaction is logged
    if transaction.transaction_date_local:
        auto_complete_on_transaction(
            db=db,
            user_id=user.id,
            transaction_date_local=transaction.transaction_date_local,
        )

    return _transaction_to_response(transaction, db)


@router.get("", response_model=TransactionListResponse)
def list_transactions_endpoint(
    date_from: Optional[date] = Query(None, description="Start date filter (inclusive)"),
    date_to: Optional[date] = Query(None, description="End date filter (inclusive)"),
    category_id: Optional[int] = Query(None, description="Category ID filter"),
    limit: int = Query(50, ge=1, le=500, description="Max results (default 50)"),
    user: User = Depends(_get_current_user),
    db: Session = Depends(get_db),
) -> TransactionListResponse:
    """List transactions with optional filters.

    Supports filtering by date range, category, and result limit.
    Returns transactions ordered by datetime descending.
    """
    transactions = get_transactions(
        db=db,
        user_id=user.id,
        date_from=date_from,
        date_to=date_to,
        category_id=category_id,
        limit=limit,
    )

    response_items = [_transaction_to_response(txn, db) for txn in transactions]

    return TransactionListResponse(
        transactions=response_items,
        count=len(response_items),
    )


@router.get("/frequent-categories", response_model=FrequentCategoriesResponse)
def get_frequent_categories_endpoint(
    user: User = Depends(_get_current_user),
    db: Session = Depends(get_db),
) -> FrequentCategoriesResponse:
    """Get up to 5 most frequently used categories from the last 30 days.

    Returns category names ordered by usage count descending.
    """
    categories = get_frequent_categories(db=db, user_id=user.id)

    return FrequentCategoriesResponse(categories=categories)


@router.post("/suggest-category", response_model=CategorySuggestionResponse)
def suggest_category_endpoint(
    request: CategorySuggestionRequest,
    user: User = Depends(_get_current_user),
    db: Session = Depends(get_db),
) -> CategorySuggestionResponse:
    """Get a category suggestion based on note and/or amount patterns.

    Returns the suggested category name or null if no suggestion is available.
    Requirements: 4.1, 4.2, 4.3, 4.4
    """
    suggested = suggest_category(
        db=db,
        user_id=user.id,
        note=request.note,
        amount=request.amount,
    )

    return CategorySuggestionResponse(suggested_category=suggested)


@router.post("/record-override", response_model=CategoryOverrideResponse)
def record_override_endpoint(
    request: CategoryOverrideRequest,
    user: User = Depends(_get_current_user),
    db: Session = Depends(get_db),
) -> CategoryOverrideResponse:
    """Record a user's category override for future suggestion prioritization.

    When a user overrides a suggested category, this stores the pattern so
    future suggestions prioritize the user's preference.
    Requirements: 4.4
    """
    record_category_override(
        db=db,
        user_id=user.id,
        category_name=request.category_name,
        note=request.note,
        amount=request.amount,
    )

    return CategoryOverrideResponse(
        success=True,
        category_name=request.category_name,
    )
