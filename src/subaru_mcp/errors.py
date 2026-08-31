"""Structured error types returned to the LLM as `[TYPE] message`."""

from __future__ import annotations

AUTH_FAILURE = "AUTH_FAILURE"
AUTH_NOT_CONFIGURED = "AUTH_NOT_CONFIGURED"
SERVICE_UNAVAILABLE = "SERVICE_UNAVAILABLE"
VEHICLE_UNAVAILABLE = "VEHICLE_UNAVAILABLE"
UNSUPPORTED = "UNSUPPORTED"
INVALID_PRESET = "INVALID_PRESET"
TIMEOUT = "TIMEOUT"
REJECTED = "REJECTED"
STALE_DATA = "STALE_DATA"
PIN_INVALID = "PIN_INVALID"
DEVICE_2FA_REQUIRED = "DEVICE_2FA_REQUIRED"

ERROR_TYPES = (
    AUTH_FAILURE,
    AUTH_NOT_CONFIGURED,
    SERVICE_UNAVAILABLE,
    VEHICLE_UNAVAILABLE,
    UNSUPPORTED,
    INVALID_PRESET,
    TIMEOUT,
    REJECTED,
    STALE_DATA,
    PIN_INVALID,
    DEVICE_2FA_REQUIRED,
)


def format_error(error_type: str, message: str) -> str:
    msg = (message or "").strip() or "request failed"
    return f"[{error_type}] {msg}"


def error_type_of(text: str) -> str | None:
    if not text.startswith("["):
        return None
    end = text.find("]")
    if end < 2:
        return None
    token = text[1:end]
    if token in ERROR_TYPES:
        return token
    return None
