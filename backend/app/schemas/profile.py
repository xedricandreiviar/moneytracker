"""Pydantic schemas for lifestyle profile API endpoints.

Requirements covered: 15.2, 15.3, 15.4, 15.5
"""

from typing import Optional

from pydantic import BaseModel, Field, field_validator, model_validator


class LifestyleProfileInput(BaseModel):
    """Request schema for PUT /api/profile (create or update lifestyle profile).

    Captures employment/income status, commute method, and conditionally vehicle type.
    vehicle_type is required only when commute_method is 'own_vehicle'.
    """

    employment_status: str = Field(
        ..., description="Employment/income status: 'student', 'working', or 'both'"
    )
    commute_method: str = Field(
        ...,
        description=(
            "Commute method: 'public_transit', 'own_vehicle', "
            "'walking_biking', or 'none_remote'"
        ),
    )
    vehicle_type: Optional[str] = Field(
        None, description="Vehicle type: 'motorcycle' or 'car' (required when commute_method is 'own_vehicle')"
    )

    @field_validator("employment_status")
    @classmethod
    def validate_employment_status(cls, v: str) -> str:
        allowed = ("student", "working", "both")
        if v not in allowed:
            raise ValueError(
                f"employment_status must be one of: {', '.join(allowed)}"
            )
        return v

    @field_validator("commute_method")
    @classmethod
    def validate_commute_method(cls, v: str) -> str:
        allowed = ("public_transit", "own_vehicle", "walking_biking", "none_remote")
        if v not in allowed:
            raise ValueError(
                f"commute_method must be one of: {', '.join(allowed)}"
            )
        return v

    @field_validator("vehicle_type")
    @classmethod
    def validate_vehicle_type(cls, v: Optional[str]) -> Optional[str]:
        if v is not None:
            allowed = ("motorcycle", "car")
            if v not in allowed:
                raise ValueError(
                    f"vehicle_type must be one of: {', '.join(allowed)}"
                )
        return v

    @model_validator(mode="after")
    def validate_vehicle_type_required(self) -> "LifestyleProfileInput":
        """vehicle_type is required when commute_method is 'own_vehicle'."""
        if self.commute_method == "own_vehicle" and self.vehicle_type is None:
            raise ValueError(
                "vehicle_type is required when commute_method is 'own_vehicle'"
            )
        if self.commute_method != "own_vehicle" and self.vehicle_type is not None:
            # Clear vehicle_type if commute_method is not own_vehicle
            self.vehicle_type = None
        return self


class LifestyleProfileResponse(BaseModel):
    """Response schema for GET /api/profile."""

    employment_status: Optional[str] = Field(
        None, description="Employment/income status"
    )
    commute_method: Optional[str] = Field(None, description="Commute method")
    vehicle_type: Optional[str] = Field(None, description="Vehicle type (if applicable)")
    profile_completed: bool = Field(
        False, description="Whether the profile questionnaire has been completed"
    )

    model_config = {"from_attributes": True}
