from typing import Any

from django.core.exceptions import (
    ValidationError as DjangoValidationError,
)
from rest_framework import status
from rest_framework.exceptions import (
    APIException,
    AuthenticationFailed,
    ErrorDetail,
    MethodNotAllowed,
    NotAuthenticated,
    NotFound,
    ParseError,
    PermissionDenied,
    Throttled,
    UnsupportedMediaType,
    ValidationError,
)
from rest_framework.response import Response
from rest_framework.views import (
    exception_handler as drf_exception_handler,
)


class APIError(APIException):
    """
    Base exception for application-level API errors.

    Use this exception in views when an application service reports
    an expected business error.

    Example:

        raise APIError(
            error_code="target_not_found",
            message="Monitoring target was not found.",
            status_code=404,
            details={
                "target_id": str(target_id),
            },
        )
    """

    status_code = status.HTTP_400_BAD_REQUEST
    default_detail = "Request failed."
    default_code = "api_error"

    def __init__(
        self,
        *,
        error_code: str,
        message: str,
        status_code: int | None = None,
        details: Any = None,
    ) -> None:
        if status_code is not None:
            self.status_code = status_code

        self.error_code = error_code
        self.error_details = details

        super().__init__(
            detail=message,
            code=error_code,
        )


def api_exception_handler(
    exc: Exception,
    context: dict[str, Any],
) -> Response | None:
    """
    Convert supported Django REST Framework exceptions to one format.

    The standard DRF exception handler is called first. It remains
    responsible for:

    - selecting the correct HTTP status;
    - authentication headers;
    - Retry-After headers;
    - handling DRF APIException subclasses;
    - handling Django Http404 and PermissionDenied exceptions.

    This function only replaces the response body.

    Returning None for an unknown exception keeps normal Django error
    handling and does not hide programming errors or tracebacks.
    """

    normalized_exception = _normalize_exception(
        exc=exc,
    )

    response = drf_exception_handler(
        normalized_exception,
        context,
    )

    if response is None:
        return None

    original_data = response.data

    response.data = {
        "success": False,
        "error_code": _get_error_code(
            exc=normalized_exception,
            status_code=response.status_code,
        ),
        "error": _get_error_message(
            exc=normalized_exception,
            response_data=original_data,
        ),
        "details": _get_error_details(
            exc=normalized_exception,
            response_data=original_data,
        ),
    }

    return response


def _normalize_exception(
    *,
    exc: Exception,
) -> Exception:
    """
    Convert Django ValidationError to DRF ValidationError.

    DRF does not process django.core.exceptions.ValidationError through
    its standard exception handler automatically.
    """

    if not isinstance(
        exc,
        DjangoValidationError,
    ):
        return exc

    if hasattr(exc, "message_dict"):
        detail = exc.message_dict

    elif hasattr(exc, "messages"):
        detail = exc.messages

    else:
        detail = str(exc)

    return ValidationError(
        detail=detail,
    )


def _get_error_code(
    *,
    exc: Exception,
    status_code: int,
) -> str:
    if isinstance(exc, APIError):
        return exc.error_code

    if isinstance(exc, ValidationError):
        return "validation_error"

    if isinstance(exc, NotAuthenticated):
        return "not_authenticated"

    if isinstance(exc, AuthenticationFailed):
        return "authentication_failed"

    if isinstance(exc, PermissionDenied):
        return "permission_denied"

    if isinstance(exc, NotFound):
        return "not_found"

    if isinstance(exc, MethodNotAllowed):
        return "method_not_allowed"

    if isinstance(exc, ParseError):
        return "parse_error"

    if isinstance(exc, UnsupportedMediaType):
        return "unsupported_media_type"

    if isinstance(exc, Throttled):
        return "throttled"

    status_code_mapping = {
        status.HTTP_400_BAD_REQUEST: "bad_request",
        status.HTTP_401_UNAUTHORIZED: "not_authenticated",
        status.HTTP_403_FORBIDDEN: "permission_denied",
        status.HTTP_404_NOT_FOUND: "not_found",
        status.HTTP_405_METHOD_NOT_ALLOWED: (
            "method_not_allowed"
        ),
        status.HTTP_409_CONFLICT: "conflict",
        status.HTTP_415_UNSUPPORTED_MEDIA_TYPE: (
            "unsupported_media_type"
        ),
        status.HTTP_429_TOO_MANY_REQUESTS: "throttled",
    }

    if status_code in status_code_mapping:
        return status_code_mapping[status_code]

    if status_code >= 500:
        return "server_error"

    return "api_error"


def _get_error_message(
    *,
    exc: Exception,
    response_data: Any,
) -> str:
    if isinstance(exc, ValidationError):
        return "Request validation failed."

    if isinstance(exc, APIError):
        return _to_message(
            value=exc.detail,
        )

    if (
        isinstance(response_data, dict)
        and "detail" in response_data
    ):
        return _to_message(
            value=response_data["detail"],
        )

    exception_detail = getattr(
        exc,
        "detail",
        None,
    )

    if exception_detail is not None:
        return _to_message(
            value=exception_detail,
        )

    return "Request failed."


def _get_error_details(
    *,
    exc: Exception,
    response_data: Any,
) -> Any:
    if isinstance(exc, APIError):
        return _to_plain_value(
            value=exc.error_details,
        )

    if isinstance(exc, ValidationError):
        return _to_plain_value(
            value=response_data,
        )

    if isinstance(exc, Throttled):
        return {
            "wait_seconds": exc.wait,
        }

    if isinstance(exc, MethodNotAllowed):
        return {
            "method": exc.method,
        }

    if isinstance(exc, UnsupportedMediaType):
        return {
            "media_type": exc.media_type,
        }

    return None


def _to_message(
    *,
    value: Any,
) -> str:
    if isinstance(value, ErrorDetail):
        return str(value)

    if isinstance(value, str):
        return value

    if isinstance(value, list):
        if not value:
            return "Request failed."

        return _to_message(
            value=value[0],
        )

    if isinstance(value, dict):
        if "detail" in value:
            return _to_message(
                value=value["detail"],
            )

        if value:
            first_value = next(
                iter(value.values())
            )
            return _to_message(
                value=first_value,
            )

    return str(value)


def _to_plain_value(
    *,
    value: Any,
) -> Any:
    """
    Convert DRF ErrorDetail objects to ordinary JSON-compatible values.
    """

    if isinstance(value, ErrorDetail):
        return str(value)

    if isinstance(value, dict):
        return {
            str(key): _to_plain_value(
                value=item,
            )
            for key, item in value.items()
        }

    if isinstance(value, list):
        return [
            _to_plain_value(
                value=item,
            )
            for item in value
        ]

    if isinstance(value, tuple):
        return [
            _to_plain_value(
                value=item,
            )
            for item in value
        ]

    return value
