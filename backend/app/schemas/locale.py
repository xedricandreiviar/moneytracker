"""Pydantic schemas for locale configuration API endpoints."""

from pydantic import BaseModel, Field


class LocaleConfigResponse(BaseModel):
    """Response schema for GET /api/settings/locale."""

    country_code: str = Field(..., description="Two-letter ISO country code")
    currency_code: str = Field(..., description="ISO 4217 currency code")
    currency_symbol: str = Field(..., description="Currency display symbol")
    decimal_precision: int = Field(..., description="Number of decimal places (0, 2, or 3)")
    decimal_separator: str = Field(..., description="Character for decimal point")
    thousands_separator: str = Field(..., description="Character for thousands grouping")
    date_format: str = Field(..., description="Date display format pattern")
    week_start_day: int = Field(..., description="Week start day (0=Sunday, 1=Monday, ..., 6=Saturday)")

    model_config = {"from_attributes": True}


class LocaleUpdateRequest(BaseModel):
    """Request schema for PUT /api/settings/locale."""

    country_code: str = Field(
        ...,
        min_length=2,
        max_length=2,
        description="Two-letter ISO country code (e.g., 'US', 'GB', 'JP')",
    )


class LocaleUpdateResponse(BaseModel):
    """Response schema for PUT /api/settings/locale."""

    message: str = Field(..., description="Confirmation message")
    locale: LocaleConfigResponse = Field(..., description="The updated locale configuration")
