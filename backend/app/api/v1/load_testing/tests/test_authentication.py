from django.contrib.auth import get_user_model
from django.test import TestCase, override_settings
from rest_framework.test import APIClient


AUTH_CLASSES = [
    "app.api.v1.load_testing.authentication.LoadTestHeaderAuthentication",
]


@override_settings(
    LOAD_TESTING_ENABLED=True,
    LOAD_TESTING_API_KEY="load-test-key-that-is-long-enough",
    REST_FRAMEWORK={
        "DEFAULT_AUTHENTICATION_CLASSES": AUTH_CLASSES,
        "DEFAULT_PERMISSION_CLASSES": [
            "rest_framework.permissions.IsAuthenticated",
        ],
    },
)
class LoadTestHeaderAuthenticationTests(TestCase):
    def setUp(self):
        self.user = get_user_model().objects.create_user(
            username="loadtest_000001",
        )
        self.client = APIClient()

    def test_load_user_can_access_authenticated_monitoring_api(self):
        response = self.client.get(
            "/api/v1/monitoring/targets/",
            HTTP_X_LOAD_TEST_KEY="load-test-key-that-is-long-enough",
            HTTP_X_LOAD_TEST_USER_ID=str(self.user.pk),
        )

        self.assertEqual(response.status_code, 200)

    def test_wrong_key_is_rejected(self):
        response = self.client.get(
            "/api/v1/monitoring/targets/",
            HTTP_X_LOAD_TEST_KEY="wrong",
            HTTP_X_LOAD_TEST_USER_ID=str(self.user.pk),
        )

        self.assertEqual(response.status_code, 401)

    def test_normal_user_cannot_be_impersonated(self):
        normal_user = get_user_model().objects.create_user(
            username="regular_user",
        )
        response = self.client.get(
            "/api/v1/monitoring/targets/",
            HTTP_X_LOAD_TEST_KEY="load-test-key-that-is-long-enough",
            HTTP_X_LOAD_TEST_USER_ID=str(normal_user.pk),
        )

        self.assertEqual(response.status_code, 401)
