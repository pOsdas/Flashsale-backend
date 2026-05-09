from rest_framework import status
from rest_framework.decorators import api_view, permission_classes
from rest_framework.response import Response
from drf_spectacular.utils import extend_schema, OpenApiResponse

from app.api.v1.fetcher.exceptions import (
    FetcherBatchAlreadyProcessedError,
    FetcherCurrencyNotSupportedError,
    FetcherError,
    FetcherImportInProgressError,
    FetcherStockUpdateError,
    FetcherUpsertError,
)
from app.api.v1.fetcher.permissions import (
    HasFetcherApiKey,
)
from app.api.v1.fetcher.serializers import FetcherImportSerializer
from app.api.v1.fetcher.services import FetcherImportService
from app.core.logging import get_logger


logger = get_logger(__name__)


@extend_schema(
    tags=["Fetcher"],
    summary="Import products from external fetcher",
    description=(
        "Receives product data from go_fetcher service and performs upsert "
        "into catalog and stock. Supports idempotency via batch_id."
    ),
    request=FetcherImportSerializer,
    responses={
        200: OpenApiResponse(
            description="Import successful or already processed",
            response={
                "type": "object",
                "properties": {
                    "success": {"type": "boolean"},
                    "status": {"type": "string"},
                    "source": {"type": "string"},
                    "batch_id": {"type": "string"},
                    "created": {"type": "integer"},
                    "updated": {"type": "integer"},
                },
            },
        ),
        400: OpenApiResponse(description="Invalid payload or unsupported currency"),
        409: OpenApiResponse(description="Import already in progress"),
        500: OpenApiResponse(description="Internal server error"),
    },
)
@api_view(["POST"])
@permission_classes([HasFetcherApiKey])
def import_fetcher_items(request):
    serializer = FetcherImportSerializer(data=request.data)

    if not serializer.is_valid():
        return Response(
            {
                "success": False,
                "error": "Invalid import payload.",
                "details": serializer.errors,
            },
            status=status.HTTP_400_BAD_REQUEST
        )

    source = serializer.validated_data["source"]
    batch_id = serializer.validated_data["batch_id"]
    items = serializer.validated_data["items"]

    logger.info(
        "Fetcher import request received",
        extra={
            "source": source,
            "batch_id": batch_id,
            "items_count": len(items),
        },
    )

    service = FetcherImportService(
        source=source,
        batch_id=batch_id,
        items=items,
    )
    try:
        result = service.execute()
    except FetcherBatchAlreadyProcessedError:
        logger.info(
            "Fetcher import batch already processed",
            extra={
                "source": source,
                "batch_id": batch_id,
            },
        )

        return Response(
            {
                "success": True,
                "status": "already_processed",
                "source": source,
                "batch_id": batch_id,
                "created": 0,
                "updated": 0,
            },
            status=status.HTTP_200_OK,
        )

    except FetcherImportInProgressError as e:
        logger.warning(
            "Fetcher import already in progress",
            extra={
                "source": source,
                "batch_id": batch_id,
            },
        )

        return Response(
            {
                "success": False,
                "error": str(e),
            },
            status=status.HTTP_409_CONFLICT,
        )

    except FetcherCurrencyNotSupportedError as e:
        logger.warning(
            "Fetcher import rejected because of unsupported currency",
            extra={
                "source": source,
                "batch_id": batch_id,
                "error": str(e),
            },
        )

        return Response(
            {
                "success": False,
                "error": str(e),
            },
            status=status.HTTP_400_BAD_REQUEST,
        )

    except (FetcherUpsertError, FetcherStockUpdateError) as e:
        logger.error(
            "Fetcher import failed during catalog update",
            extra={
                "source": source,
                "batch_id": batch_id,
                "error": str(e),
            },
            exc_info=True,
        )

        return Response(
            {
                "success": False,
                "error": "Catalog import failed.",
            },
            status=status.HTTP_500_INTERNAL_SERVER_ERROR,
        )

    except FetcherError as e:
        logger.error(
            "Fetcher import failed",
            extra={
                "source": source,
                "batch_id": batch_id,
                "error": str(e),
            },
            exc_info=True,
        )

        return Response(
            {
                "success": False,
                "error": "Fetcher import failed."
            },
            status=status.HTTP_500_INTERNAL_SERVER_ERROR,
        )

    logger.info(
        "Fetcher import completed",
        extra={
            "source": source,
            "batch_id": batch_id,
            "created_count": result["created"],
            "updated_count": result["updated"],
        },
    )

    return Response(
        {
            "success": True,
            "status": "imported",
            "source": source,
            "batch_id": batch_id,
            "created": result["created"],
            "updated": result["updated"],
        },
        status=status.HTTP_200_OK,
    )