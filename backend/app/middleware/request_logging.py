"""Request-logging middleware (MW-01 / MW-02 / MW-03).

Logs per request: method, path, response status, duration, request ID.
Never logs: Authorization headers, tokens, passwords, API keys, or full
delivery addresses (D4 / D23). Paths may contain resource ids only.

The request ID is taken from the client's `X-Request-Id` header if present,
otherwise generated, and echoed back in the response (MW-03).
"""
import logging
import time
import uuid

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request

logger = logging.getLogger("campusbite.request")


class RequestLoggingMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        request_id = request.headers.get("X-Request-Id") or uuid.uuid4().hex
        start = time.perf_counter()
        try:
            response = await call_next(request)
        except Exception:
            logger.warning(
                "request failed method=%s path=%s request_id=%s",
                request.method,
                request.url.path,
                request_id,
            )
            raise
        duration_ms = (time.perf_counter() - start) * 1000.0
        response.headers["X-Request-Id"] = request_id
        logger.info(
            "method=%s path=%s status=%d duration_ms=%.1f request_id=%s",
            request.method,
            request.url.path,
            response.status_code,
            duration_ms,
            request_id,
        )
        return response
