"""Pydantic schemas for auth endpoints."""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field

from .constants import UserRole


class PasswordVerifyRequest(BaseModel):
    """Request body for password verification."""

    model_config = ConfigDict(frozen=True)

    password: str = Field(..., description="Site password to verify")


class PasswordVerifyResponse(BaseModel):
    """Response from password verification."""

    model_config = ConfigDict(frozen=True)

    valid: bool = Field(..., description="Whether the password is valid")
    password_required: bool = Field(..., description="Whether password is required")


class AuthStatusResponse(BaseModel):
    """Response for auth status check."""

    model_config = ConfigDict(frozen=True)

    password_required: bool = Field(..., description="Whether password is required")


class UserLoginRequest(BaseModel):
    """Request body for user login (Variant B)."""

    model_config = ConfigDict(frozen=True)

    username: str = Field(..., min_length=1, max_length=100)
    password: str | None = Field(
        default=None,
        description="Site password. Required if SITE_PASSWORD is configured.",
    )


class UserResponseBase(BaseModel):
    """Base schema for user response. Apps should extend this."""

    model_config = ConfigDict(frozen=True)

    id: int
    username: str
    role: UserRole
    is_active: bool


class SessionLoginRequest(BaseModel):
    """Request body for session-based login."""

    model_config = ConfigDict(frozen=True)

    username: str = Field(..., min_length=1, max_length=100)
    password: str | None = Field(
        default=None,
        description="Site password. Required if SITE_PASSWORD is configured.",
    )


class SessionLoginResponse(BaseModel):
    """Response from session login."""

    model_config = ConfigDict(frozen=True)

    success: bool = Field(..., description="Whether login was successful")
    username: str = Field(..., description="The logged-in username")
    expires_in_seconds: int = Field(..., description="Session lifetime in seconds")
