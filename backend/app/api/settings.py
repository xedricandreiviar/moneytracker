"""API endpoints for user locale/settings configuration.

Provides GET and PUT for /api/settings/locale to read and update
the user's country-based locale configuration.
"""

from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.database import get_db
from app.models.user import User
from app.models.user_locale import UserLocale
from app.schemas.locale import (
    LocaleConfigResponse,
    LocaleUpdateRequest,
    LocaleUpdateResponse,
)
from app.services.locale_service import LOCALE_CONFIGS, get_locale_config

router = APIRouter(prefix="/api/settings", tags=["settings"])


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


@router.get("/locale", response_model=LocaleConfigResponse)
def get_user_locale(
    user: User = Depends(_get_current_user),
    db: Session = Depends(get_db),
) -> LocaleConfigResponse:
    """Return the current user's locale configuration.

    Returns 404 if the user has not yet selected a country (onboarding incomplete).
    """
    locale = db.query(UserLocale).filter(UserLocale.user_id == user.id).first()
    if not locale:
        raise HTTPException(
            status_code=404,
            detail="Locale not configured. Please complete onboarding by selecting a country.",
        )
    return LocaleConfigResponse(
        country_code=locale.country_code,
        currency_code=locale.currency_code,
        currency_symbol=locale.currency_symbol,
        decimal_precision=locale.decimal_precision,
        decimal_separator=locale.decimal_separator,
        thousands_separator=locale.thousands_separator,
        date_format=locale.date_format,
        week_start_day=locale.week_start_day,
    )


@router.put("/locale", response_model=LocaleUpdateResponse)
def update_user_locale(
    request: LocaleUpdateRequest,
    user: User = Depends(_get_current_user),
    db: Session = Depends(get_db),
) -> LocaleUpdateResponse:
    """Update the user's country selection and cascade locale settings.

    Looks up the country_code in LOCALE_CONFIGS and creates or updates
    the UserLocale record with all derived settings.

    Returns 400 if the country code is not supported.
    """
    country_code = request.country_code.upper()

    if country_code not in LOCALE_CONFIGS:
        supported = sorted(LOCALE_CONFIGS.keys())
        raise HTTPException(
            status_code=400,
            detail=f"Unsupported country code: '{country_code}'. Supported countries: {', '.join(supported)}",
        )

    locale_config = get_locale_config(country_code)

    # Find existing locale record or create new one
    locale = db.query(UserLocale).filter(UserLocale.user_id == user.id).first()
    if locale:
        locale.country_code = country_code
        locale.currency_code = locale_config.currency_code
        locale.currency_symbol = locale_config.symbol
        locale.decimal_precision = locale_config.decimal_precision
        locale.decimal_separator = locale_config.decimal_separator
        locale.thousands_separator = locale_config.thousands_separator
        locale.date_format = locale_config.date_format
        locale.week_start_day = locale_config.week_start_day
        locale.updated_at_utc = datetime.utcnow()
    else:
        locale = UserLocale(
            user_id=user.id,
            country_code=country_code,
            currency_code=locale_config.currency_code,
            currency_symbol=locale_config.symbol,
            decimal_precision=locale_config.decimal_precision,
            decimal_separator=locale_config.decimal_separator,
            thousands_separator=locale_config.thousands_separator,
            date_format=locale_config.date_format,
            week_start_day=locale_config.week_start_day,
        )
        db.add(locale)

    db.commit()
    db.refresh(locale)

    response_locale = LocaleConfigResponse(
        country_code=locale.country_code,
        currency_code=locale.currency_code,
        currency_symbol=locale.currency_symbol,
        decimal_precision=locale.decimal_precision,
        decimal_separator=locale.decimal_separator,
        thousands_separator=locale.thousands_separator,
        date_format=locale.date_format,
        week_start_day=locale.week_start_day,
    )

    return LocaleUpdateResponse(
        message=f"Locale updated to {country_code} successfully.",
        locale=response_locale,
    )
