from django.core.exceptions import (
    ValidationError as DjangoValidationError,
)
from django.test import override_settings
from django.urls import path
from rest_framework import permissions, serializers, status
from rest_framework.exceptions import (
    NotFound,
    PermissionDenied,
    Throttled,
)
from rest_framework.response import Response
from rest_framework.test import APITestCase
from rest_framework.views import APIView

from app.api.exceptions import (
    APIError,
    api_exception_handler,
)


class ValidationPayloadSerializer(
    serializers.Serializer,
):
    name = serializers.CharField()
    quantity = serializers.IntegerField(
        min_value=1,
    )


class ValidationErrorView(APIView):
    def post(
        self,
        request,
    ):
        serializer = ValidationPayloadSerializer(
            data=request.data,
        )
        serializer.is_valid(
            raise_exception=True,
        )

        return Response(
            serializer.validated_data,
        )


class AuthenticationRequiredView(APIView):
    permission_classes = [
        permissions.IsAuthenticated,
    ]

    def get(
        self,
        request,
    ):
        return Response(
            {
                "success": True,
            }
        )


class PermissionDeniedView(APIView):
    def get(
        self,
        request,
    ):
        raise PermissionDenied(
            "Access denied.",
        )


class NotFoundView(APIView):
    def get(
        self,
        request,
    ):
        raise NotFound(
            "Object was not found.",
        )


class MethodView(APIView):
    def get(
        self,
        request,
    ):
        return Response(
            {
                "success": True,
            }
        )


class ParseErrorView(APIView):
    def post(
        self,
        request,
    ):
        request.data

        return Response(
            {
                "success": True,
            }
        )


class UnsupportedMediaTypeView(APIView):
    def post(
        self,
        request,
    ):
        request.data

        return Response(
            {
                "success": True,
            }
        )


class ThrottledView(APIView):
    def get(
        self,
        request,
    ):
        raise Throttled(
            wait=15,
            detail="Too many requests.",
        )


class CustomAPIErrorView(APIView):
    def get(
        self,
        request,
    ):
        raise APIError(
            error_code="target_not_found",
            message=(
                "Monitoring target was not found."
            ),
            status_code=status.HTTP_404_NOT_FOUND,
            details={
                "target_id": "test-target-id",
            },
        )


class DjangoValidationErrorView(APIView):
    def get(
        self,
        request,
    ):
        raise DjangoValidationError(
            {
                "external_id": [
                    "External id is invalid.",
                ],
            }
        )


class ManualErrorResponseView(APIView):
    def get(
        self,
        request,
    ):
        return Response(
            {
                "success": False,
                "error_code": "legacy_error",
                "error": "Legacy error response.",
            },
            status=status.HTTP_400_BAD_REQUEST,
        )


urlpatterns = [
    path(
        "validation/",
        ValidationErrorView.as_view(),
    ),
    path(
        "authentication/",
        AuthenticationRequiredView.as_view(),
    ),
    path(
        "permission-denied/",
        PermissionDeniedView.as_view(),
    ),
    path(
        "not-found/",
        NotFoundView.as_view(),
    ),
    path(
        "method/",
        MethodView.as_view(),
    ),
    path(
        "parse-error/",
        ParseErrorView.as_view(),
    ),
    path(
        "unsupported-media-type/",
        UnsupportedMediaTypeView.as_view(),
    ),
    path(
        "throttled/",
        ThrottledView.as_view(),
    ),
    path(
        "custom-error/",
        CustomAPIErrorView.as_view(),
    ),
    path(
        "django-validation/",
        DjangoValidationErrorView.as_view(),
    ),
    path(
        "manual-response/",
        ManualErrorResponseView.as_view(),
    ),
]


@override_settings(
    ROOT_URLCONF=__name__,
)
class APIExceptionHandlerTests(APITestCase):
    def test_serializer_validation_error_has_common_format(
        self,
    ):
        response = self.client.post(
            "/validation/",
            data={},
            format="json",
        )

        self.assertEqual(
            response.status_code,
            status.HTTP_400_BAD_REQUEST,
        )
        self.assertFalse(
            response.data["success"],
        )
        self.assertEqual(
            response.data["error_code"],
            "validation_error",
        )
        self.assertEqual(
            response.data["error"],
            "Request validation failed.",
        )
        self.assertIn(
            "name",
            response.data["details"],
        )
        self.assertIn(
            "quantity",
            response.data["details"],
        )

    def test_not_authenticated_error_has_common_format(
        self,
    ):
        response = self.client.get(
            "/authentication/",
        )

        self.assertIn(
            response.status_code,
            (
                status.HTTP_401_UNAUTHORIZED,
                status.HTTP_403_FORBIDDEN,
            ),
        )
        self.assertFalse(
            response.data["success"],
        )
        self.assertEqual(
            response.data["error_code"],
            "not_authenticated",
        )
        self.assertIsNone(
            response.data["details"],
        )

    def test_permission_denied_error_has_common_format(
        self,
    ):
        response = self.client.get(
            "/permission-denied/",
        )

        self.assertEqual(
            response.status_code,
            status.HTTP_403_FORBIDDEN,
        )
        self.assertFalse(
            response.data["success"],
        )
        self.assertEqual(
            response.data["error_code"],
            "permission_denied",
        )
        self.assertEqual(
            response.data["error"],
            "Access denied.",
        )

    def test_not_found_error_has_common_format(
        self,
    ):
        response = self.client.get(
            "/not-found/",
        )

        self.assertEqual(
            response.status_code,
            status.HTTP_404_NOT_FOUND,
        )
        self.assertFalse(
            response.data["success"],
        )
        self.assertEqual(
            response.data["error_code"],
            "not_found",
        )
        self.assertEqual(
            response.data["error"],
            "Object was not found.",
        )
        self.assertIsNone(
            response.data["details"],
        )

    def test_method_not_allowed_has_common_format(
        self,
    ):
        response = self.client.post(
            "/method/",
            data={},
            format="json",
        )

        self.assertEqual(
            response.status_code,
            status.HTTP_405_METHOD_NOT_ALLOWED,
        )
        self.assertFalse(
            response.data["success"],
        )
        self.assertEqual(
            response.data["error_code"],
            "method_not_allowed",
        )
        self.assertEqual(
            response.data["details"]["method"],
            "POST",
        )

    def test_invalid_json_has_common_format(
        self,
    ):
        response = self.client.generic(
            method="POST",
            path="/parse-error/",
            data='{"name":',
            content_type="application/json",
        )

        self.assertEqual(
            response.status_code,
            status.HTTP_400_BAD_REQUEST,
        )
        self.assertFalse(
            response.data["success"],
        )
        self.assertEqual(
            response.data["error_code"],
            "parse_error",
        )
        self.assertIsNone(
            response.data["details"],
        )

    def test_unsupported_media_type_has_common_format(
        self,
    ):
        response = self.client.generic(
            method="POST",
            path="/unsupported-media-type/",
            data="<request />",
            content_type="application/xml",
        )

        self.assertEqual(
            response.status_code,
            status.HTTP_415_UNSUPPORTED_MEDIA_TYPE,
        )
        self.assertFalse(
            response.data["success"],
        )
        self.assertEqual(
            response.data["error_code"],
            "unsupported_media_type",
        )
        self.assertEqual(
            response.data["details"]["media_type"],
            "application/xml",
        )

    def test_throttled_error_preserves_retry_after_header(
        self,
    ):
        response = self.client.get(
            "/throttled/",
        )

        self.assertEqual(
            response.status_code,
            status.HTTP_429_TOO_MANY_REQUESTS,
        )
        self.assertFalse(
            response.data["success"],
        )
        self.assertEqual(
            response.data["error_code"],
            "throttled",
        )
        self.assertEqual(
            response.data["details"]["wait_seconds"],
            15,
        )
        self.assertEqual(
            response.headers["Retry-After"],
            "15",
        )

    def test_custom_api_error_has_common_format(
        self,
    ):
        response = self.client.get(
            "/custom-error/",
        )

        self.assertEqual(
            response.status_code,
            status.HTTP_404_NOT_FOUND,
        )
        self.assertFalse(
            response.data["success"],
        )
        self.assertEqual(
            response.data["error_code"],
            "target_not_found",
        )
        self.assertEqual(
            response.data["error"],
            "Monitoring target was not found.",
        )
        self.assertEqual(
            response.data["details"],
            {
                "target_id": "test-target-id",
            },
        )

    def test_django_validation_error_is_supported(
        self,
    ):
        response = self.client.get(
            "/django-validation/",
        )

        self.assertEqual(
            response.status_code,
            status.HTTP_400_BAD_REQUEST,
        )
        self.assertFalse(
            response.data["success"],
        )
        self.assertEqual(
            response.data["error_code"],
            "validation_error",
        )
        self.assertEqual(
            response.data["details"],
            {
                "external_id": [
                    "External id is invalid.",
                ],
            },
        )

    def test_manual_response_is_not_modified(
        self,
    ):
        response = self.client.get(
            "/manual-response/",
        )

        self.assertEqual(
            response.status_code,
            status.HTTP_400_BAD_REQUEST,
        )
        self.assertEqual(
            response.data,
            {
                "success": False,
                "error_code": "legacy_error",
                "error": "Legacy error response.",
            },
        )

    def test_unknown_exception_is_not_hidden(
        self,
    ):
        response = api_exception_handler(
            RuntimeError(
                "Unexpected programming error.",
            ),
            context={},
        )

        self.assertIsNone(
            response,
        )
