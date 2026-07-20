"""Typed errors -> structured JSON. The panel should never see a stack trace."""

from __future__ import annotations


class AdvisorError(Exception):
    """Base class for errors we can describe to the client safely."""

    error_code = "advisor_error"
    retryable = False
    public_message = "The advisor could not complete your request."

    def __init__(self, message: str | None = None) -> None:
        super().__init__(message or self.public_message)
        self.detail = message or self.public_message


class UpstreamTimeout(AdvisorError):
    error_code = "upstream_timeout"
    retryable = True
    public_message = "The advisor took too long to respond. Please try again."


class UpstreamUnavailable(AdvisorError):
    error_code = "upstream_unavailable"
    retryable = True
    public_message = "The advisor is temporarily unavailable. Please try again."


class AuthNotConfigured(AdvisorError):
    error_code = "auth_not_configured"
    retryable = False
    public_message = (
        "The advisor's cloud credentials are not configured. "
        "Run `gcloud auth application-default login`."
    )


class EmptyResponse(AdvisorError):
    error_code = "empty_response"
    retryable = True
    public_message = "The advisor returned an empty answer. Please try again."


def classify(exc: Exception) -> AdvisorError:
    """Map an arbitrary upstream exception onto our typed set."""
    if isinstance(exc, AdvisorError):
        return exc
    if isinstance(exc, TimeoutError):
        return UpstreamTimeout()

    text = f"{type(exc).__name__}: {exc}".lower()
    auth_markers = (
        "default credentials",
        "could not automatically determine credentials",
        "unauthenticated",
        "permission denied",
        "403",
        "reauth",
    )
    if any(m in text for m in auth_markers):
        return AuthNotConfigured()
    transient = ("503", "502", "504", "unavailable", "deadline", "timeout",
                 "resource_exhausted", "429", "rate limit")
    if any(m in text for m in transient):
        return UpstreamUnavailable()
    return AdvisorError()


def is_retryable(exc: Exception) -> bool:
    return classify(exc).retryable
