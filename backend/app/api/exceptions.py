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
    Base exception for expected application-level API errors.

    The standard DRF exception handler still controls the HTTP response
    status and headers. The custom handler converts the response body
    to the common API error format.
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
    Convert supported DRF exceptions to a common response format.

    DRF remains responsible for:
    - selecting the HTTP status;
    - authentication headers;
    - Retry-After headers;
    - Http404 and permission handling.

    Unknown programming errors are not hidden. Returning None delegates
    them back to Django so traceback and normal logging remain available.
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
            context=context,
        ),
    }

    return response


def _normalize_exception(
    *,
    exc: Exception,
) -> Exception:
    """
    Convert django.core.exceptions.ValidationError to the DRF version.

    Django ValidationError is not automatically processed by the
    standard DRF exception handler.
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
    context: dict[str, Any],
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
            "method": _get_request_method(
                context=context,
            ),
        }

    if isinstance(exc, UnsupportedMediaType):
        return {
            "media_type": _get_request_content_type(
                context=context,
            ),
        }

    return None


def _get_request_method(
    *,
    context: dict[str, Any],
) -> str | None:
    """
    Read the HTTP method from the request passed by DRF.

    MethodNotAllowed does not guarantee that the original method is
    available as exc.method in every DRF version.
    """

    request = context.get("request")

    if request is None:
        return None

    method = getattr(
        request,
        "method",
        None,
    )

    if method is None:
        return None

    return str(method).upper()


def _get_request_content_type(
    *,
    context: dict[str, Any],
) -> str | None:
    """
    Read Content-Type from the request passed by DRF.

    UnsupportedMediaType does not guarantee that the original media
    type is available as exc.media_type in every DRF version.
    """

    request = context.get("request")

    if request is None:
        return None

    content_type = getattr(
        request,
        "content_type",
        None,
    )

    if content_type:
        return str(content_type)

    meta = getattr(
        request,
        "META",
        {},
    )

    content_type = meta.get(
        "CONTENT_TYPE",
    )

    if content_type:
        return str(content_type)

    underlying_request = getattr(
        request,
        "_request",
        None,
    )

    if underlying_request is None:
        return None

    underlying_content_type = getattr(
        underlying_request,
        "content_type",
        None,
    )

    if underlying_content_type:
        return str(underlying_content_type)

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
    Convert DRF ErrorDetail objects to JSON-compatible values.
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
