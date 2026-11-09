"""The API error format (D14).

Every error body is exactly:

    {"detail": "<human-readable sentence>", "code": "<MACHINE_CODE>"}

`code` is a stable token the frontend branches on (e.g. `INVALID_TRANSITION`,
`IDEMPOTENCY_MISMATCH`); `detail` is what a human reads. Internal errors never
leak stack traces or configuration (D9).
"""
from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException


class ApiError(Exception):
    """Business-rule failure with a machine-readable code."""

    def __init__(self, status_code: int, code: str, detail: str):
        self.status_code = status_code
        self.code = code
        self.detail = detail
        super().__init__(detail)


def _response(status_code: int, code: str, detail: str) -> JSONResponse:
    return JSONResponse(
        status_code=status_code,
        content={"detail": detail, "code": code},
    )


def register_error_handlers(app: FastAPI) -> None:
    @app.exception_handler(ApiError)
    async def _api_error(request: Request, exc: ApiError) -> JSONResponse:
        return _response(exc.status_code, exc.code, exc.detail)

    @app.exception_handler(RequestValidationError)
    async def _validation(
        request: Request, exc: RequestValidationError
    ) -> JSONResponse:
        errors = exc.errors()
        first = errors[0] if errors else {}
        loc = " → ".join(str(p) for p in first.get("loc", ()) if p != "body")
        msg = str(first.get("msg", "Invalid request"))
        detail = f"{loc}: {msg}" if loc else msg
        return _response(422, "VALIDATION_ERROR", detail)

    @app.exception_handler(StarletteHTTPException)
    async def _http(request: Request, exc: StarletteHTTPException) -> JSONResponse:
        headers = getattr(exc, "headers", None)
        return JSONResponse(
            status_code=exc.status_code,
            content={"detail": exc.detail, "code": "HTTP_ERROR"},
            headers=headers,
        )

    @app.exception_handler(Exception)
    async def _internal(request: Request, exc: Exception) -> JSONResponse:
        # Controlled fallback: log internally, reveal nothing (D9).
        import logging

        logging.getLogger("campusbite.error").exception(
            "unhandled error on %s %s", request.method, request.url.path
        )
        return _response(500, "INTERNAL", "An internal error occurred.")
