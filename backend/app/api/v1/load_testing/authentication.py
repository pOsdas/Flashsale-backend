import secrets

from django.conf import settings
from django.contrib.auth import get_user_model
from rest_framework.authentication import BaseAuthentication
from rest_framework.exceptions import AuthenticationFailed


class LoadTestHeaderAuthentication(BaseAuthentication):
    """
    Authenticate synthetic users only inside the isolated Load Lab.

    The class is added to DRF only when LOAD_TESTING_ENABLED=true. Every
    request must provide both headers:

    - X-Load-Test-Key
    - X-Load-Test-User-ID

    The API key prevents accidental use even when someone exposes a local
    load-test container. Normal project startup does not enable this class.
    """

    key_header = "HTTP_X_LOAD_TEST_KEY"

    def authenticate(self, request):
        if not getattr(settings, "LOAD_TESTING_ENABLED", False):
            return None

        supplied_key = str(
            request.META.get(self.key_header, "") or ""
        ).strip()
        expected_key = str(
            getattr(settings, "LOAD_TESTING_API_KEY", "") or ""
        ).strip()

        if not supplied_key and not request.META.get(
            getattr(
                settings,
                "LOAD_TESTING_USER_HEADER",
                "HTTP_X_LOAD_TEST_USER_ID",
            ),
            "",
        ):
            return None

        if not expected_key or not secrets.compare_digest(
            supplied_key,
            expected_key,
        ):
            raise AuthenticationFailed("Invalid load-test API key.")

        user_header = getattr(
            settings,
            "LOAD_TESTING_USER_HEADER",
            "HTTP_X_LOAD_TEST_USER_ID",
        )
        raw_user_id = str(
            request.META.get(user_header, "") or ""
        ).strip()

        if not raw_user_id.isdigit():
            raise AuthenticationFailed(
                "X-Load-Test-User-ID must contain a numeric user ID."
            )

        user_model = get_user_model()

        try:
            user = user_model.objects.get(
                pk=int(raw_user_id),
                is_active=True,
                username__startswith="loadtest_",
            )
        except user_model.DoesNotExist as exc:
            raise AuthenticationFailed(
                "Synthetic load-test user was not found."
            ) from exc

        return user, "load-test-header"

    def authenticate_header(self, request) -> str:
        return "LoadTest"
