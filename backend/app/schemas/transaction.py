"""Pydantic schemas for transaction API endpoints."""

import json
from datetime import date, datetime
from typing import Optional

from pydantic import BaseModel, Field, field_validator


class TransactionCreateRequest(BaseModel):
    """Request schema for POST /api/transactions."""

    amount_smallest_unit: int = Field(
        ..., gt=0, description="Positive integer amount in smallest currency unit"
    )
    direction: str = Field(
        ..., description="Transaction direction: 'spent' or 'received'"
    )
    currency_code: str = Field(
        ..., min_length=3, max_length=3, description="ISO 4217 currency code"
    )
    category_name: Optional[str] = Field(
        None, max_length=100, description="Optional category name"
    )
    note: Optional[str] = Field(
        None, max_length=200, description="Optional note (max 200 characters)"
    )
    payment_method: Optional[str] = Field(
        None, max_length=50, description="Optional payment method"
    )
    tags: Optional[list[str]] = Field(
        None, max_length=10, description="Optional list of tags (max 10)"
    )

    @field_validator("direction")
    @classmethod
    def validate_direction(cls, v: str) -> str:
        if v not in ("spent", "received"):
            raise ValueError("Direction must be 'spent' or 'received'.")
        return v

    @field_validator("tags")
    @classmethod
    def validate_tags_length(cls, v: Optional[list[str]]) -> Optional[list[str]]:
        if v is not None and len(v) > 10:
            raise ValueError("Maximum 10 tags allowed.")
        return v


class TransactionResponse(BaseModel):
    """Response schema for a single transaction."""

    id: int
    user_id: int
    amount_smallest_unit: int
    direction: str
    currency_code: str
    category_name: Optional[str] = None
    note: Optional[str] = None
    payment_method: Optional[str] = None
    tags: Optional[list[str]] = None
    transaction_datetime_utc: datetime
    transaction_date_local: date
    created_at_utc: datetime

    model_config = {"from_attributes": True}


class TransactionListResponse(BaseModel):
    """Response schema for GET /api/transactions."""

    transactions: list[TransactionResponse]
    count: int


class FrequentCategoriesResponse(BaseModel):
    """Response schema for GET /api/transactions/frequent-categories."""

    categories: list[str]


class ValidationErrorDetail(BaseModel):
    """Detail schema for field-level validation errors."""

    field: str = Field(..., description="The field that failed validation")
    message: str = Field(..., description="Error message describing the constraint")


class CategorySuggestionRequest(BaseModel):
    """Request schema for POST /api/transactions/suggest-category."""

    note: Optional[str] = Field(
        None, max_length=200, description="Transaction note to match against history"
    )
    amount: Optional[int] = Field(
        None, gt=0, description="Transaction amount in smallest currency unit"
    )


class CategorySuggestionResponse(BaseModel):
    """Response schema for POST /api/transactions/suggest-category."""

    suggested_category: Optional[str] = Field(
        None, description="Suggested category name, or null if no suggestion"
    )


class CategoryOverrideRequest(BaseModel):
    """Request schema for POST /api/transactions/record-override."""

    category_name: str = Field(
        ..., min_length=1, max_length=100, description="The category the user chose"
    )
    note: Optional[str] = Field(
        None, max_length=200, description="Transaction note for pattern matching"
    )
    amount: Optional[int] = Field(
        None, gt=0, description="Transaction amount for pattern matching"
    )


class CategoryOverrideResponse(BaseModel):
    """Response schema for POST /api/transactions/record-override."""

    success: bool = Field(..., description="Whether the override was recorded")
    category_name: str = Field(..., description="The category that was recorded")
