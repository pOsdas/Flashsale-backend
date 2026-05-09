from app.core.config import get_settings
from rest_framework.permissions import BasePermission


settings = get_settings()


class HasFetcherApiKey(BasePermission):
    message = "Invalid or missing fetcher API key."

    def has_permission(self, request, view) -> bool:
        expected_api_key = settings.fetcher_api_key

        if not expected_api_key:
            return False

        provided_api_key = request.headers.get(
            "X-Fetcher-Api-Key"
        )

        if not provided_api_key:
            return False

        return provided_api_key == expected_api_key
