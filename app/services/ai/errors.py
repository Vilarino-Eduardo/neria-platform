from openai import (
    APIConnectionError,
    APIStatusError,
    APITimeoutError,
    AuthenticationError,
    BadRequestError,
    RateLimitError,
)


def safe_ai_error_code(error: Exception) -> str:
    """Classify provider failures without persisting third-party error details."""
    if isinstance(error, AuthenticationError):
        return "provider_authentication_failed"
    if isinstance(error, RateLimitError):
        return (
            "provider_quota_exhausted"
            if getattr(error, "code", None) == "insufficient_quota"
            else "provider_rate_limited"
        )
    if isinstance(error, APITimeoutError):
        return "provider_timeout"
    if isinstance(error, APIConnectionError):
        return "provider_unavailable"
    if isinstance(error, BadRequestError):
        return "provider_request_rejected"
    if isinstance(error, APIStatusError):
        return "provider_http_error"
    return "provider_error"
