"""HTTP middleware: reject over-large request bodies early."""

from __future__ import annotations

from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint
from starlette.requests import Request
from starlette.responses import JSONResponse, Response
from starlette.types import ASGIApp


class BodySizeLimitMiddleware(BaseHTTPMiddleware):
    """Reject requests whose declared Content-Length exceeds a byte cap (413).

    A malformed or negative Content-Length is rejected (400) rather than allowed
    through — a forgeable header must never silently bypass the size cap.
    """

    def __init__(self, app: ASGIApp, max_bytes: int) -> None:
        super().__init__(app)
        self._max_bytes = max_bytes

    async def dispatch(self, request: Request, call_next: RequestResponseEndpoint) -> Response:
        content_length = request.headers.get("content-length")
        if content_length is not None:
            try:
                declared = int(content_length)
            except ValueError:
                declared = -1
            if declared < 0:
                return JSONResponse({"detail": "Invalid Content-Length header"}, status_code=400)
            if declared > self._max_bytes:
                return JSONResponse({"detail": "Request body too large"}, status_code=413)
        return await call_next(request)
