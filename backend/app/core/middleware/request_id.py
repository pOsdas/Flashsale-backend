from app.core.logging import get_logger
import time
import uuid

from app.core.logging_context import clear_request_id, set_request_id

logger = get_logger("backend.request")


class RequestIDMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        started_at = time.perf_counter()

        request_id = request.headers.get("X-Request-ID") or str(uuid.uuid4())
        request.request_id = request_id
        set_request_id(request_id)

        try:
            response = self.get_response(request)

            duration_ms = round((time.perf_counter() - started_at) * 1000, 2)

            response["X-Request-ID"] = request_id

            logger.info(
                "http request completed",
                extra={
                    "service": "backend",
                    "request_id": request_id,
                    "method": request.method,
                    "path": request.path,
                    "status_code": response.status_code,
                    "duration_ms": duration_ms,
                },
            )

            return response

        finally:
            clear_request_id()
