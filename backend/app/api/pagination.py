from collections import OrderedDict
from typing import Any

from rest_framework.pagination import PageNumberPagination
from rest_framework.response import Response


class StandardPageNumberPagination(PageNumberPagination):
    """
    Standard pagination for API list endpoints.

    Query parameters:
    - page: requested page number;
    - page_size: number of objects per page.

    A client cannot request more than max_page_size objects.
    """

    page_size = 20
    page_query_param = "page"
    page_size_query_param = "page_size"
    max_page_size = 100

    def get_paginated_response(
        self,
        data: list[Any],
    ) -> Response:
        return Response(
            OrderedDict(
                [
                    (
                        "count",
                        self.page.paginator.count,
                    ),
                    (
                        "page",
                        self.page.number,
                    ),
                    (
                        "page_size",
                        self.page.paginator.per_page,
                    ),
                    (
                        "total_pages",
                        self.page.paginator.num_pages,
                    ),
                    (
                        "next",
                        self.get_next_link(),
                    ),
                    (
                        "previous",
                        self.get_previous_link(),
                    ),
                    (
                        "results",
                        data,
                    ),
                ]
            )
        )

    def get_paginated_response_schema(
        self,
        schema: dict[str, Any],
    ) -> dict[str, Any]:
        """
        Describe the custom pagination response for OpenAPI.
        """

        return {
            "type": "object",
            "required": [
                "count",
                "page",
                "page_size",
                "total_pages",
                "results",
            ],
            "properties": {
                "count": {
                    "type": "integer",
                    "example": 57,
                },
                "page": {
                    "type": "integer",
                    "example": 1,
                },
                "page_size": {
                    "type": "integer",
                    "example": 20,
                },
                "total_pages": {
                    "type": "integer",
                    "example": 3,
                },
                "next": {
                    "type": "string",
                    "nullable": True,
                    "format": "uri",
                    "example": (
                        "http://localhost:8000/"
                        "api/v1/monitoring/targets/?page=2"
                    ),
                },
                "previous": {
                    "type": "string",
                    "nullable": True,
                    "format": "uri",
                    "example": None,
                },
                "results": schema,
            },
        }
