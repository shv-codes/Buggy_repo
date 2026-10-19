import json
import logging
import sys
import time
from datetime import datetime, timezone

_STANDARD_ATTRS = set(vars(logging.makeLogRecord({}))) | {"message", "asctime"}


class JsonFormatter(logging.Formatter):
    """Formats log records as single-line JSON objects."""

    def format(self, record):
        ts = datetime.fromtimestamp(record.created, tz=timezone.utc).isoformat()
        payload = {
            "ts": ts,
            "level": record.levelname,
            "method": getattr(record, "method", "INTERNAL"),
            "path": getattr(record, "path", "-"),
            "status": getattr(record, "status", 200),
            "duration_ms": getattr(record, "duration_ms", 0.0),
            "module": getattr(record, "module_path", "analytics/views.py"),
            "function": getattr(record, "func_name", getattr(record, "funcName", "-")),
            "error": getattr(record, "error", None),
        }
        return json.dumps(payload)


request_logger = logging.getLogger("victim.request")


class RequestLogMiddleware:
    """Logs each request as JSON, capturing view path and operational errors."""

    def __init__(self, get_response):
        self.get_response = get_response

    def process_exception(self, request, exception):
        request._caught_exception = exception
        return None

    def __call__(self, request):
        started = time.monotonic()
        error_msg = None
        response = None
        status_code = 200

        try:
            response = self.get_response(request)
            status_code = response.status_code
        except Exception as exc:
            error_msg = str(exc)
            status_code = 500
            from django.http import JsonResponse
            response = JsonResponse({"error": error_msg}, status=500)

        # Check if an exception was caught by process_exception
        caught_exc = getattr(request, "_caught_exception", None)
        if caught_exc is not None:
            error_msg = str(caught_exc)
            status_code = max(status_code, 500)

        duration_ms = round((time.monotonic() - started) * 1000, 2)
        match = getattr(request, "resolver_match", None)
        func_name = getattr(match, "func", None).__name__ if match and hasattr(match, "func") else "unknown"

        level = "ERROR" if status_code >= 500 else "INFO"

        extra = {
            "method": request.method,
            "path": request.path,
            "status": status_code,
            "duration_ms": duration_ms,
            "module_path": "analytics/views.py",
            "func_name": func_name,
            "error": error_msg,
        }

        if level == "ERROR":
            request_logger.error(f"{request.method} {request.path} failed: {error_msg}", extra=extra)
        else:
            request_logger.info(f"{request.method} {request.path} {status_code}", extra=extra)

        # Check for unclosed cursor connection leak in PostgreSQL
        from django.db import connection
        active_cursors = getattr(connection, "_active_cursors", None)
        if active_cursors and len(active_cursors) > 0:
            if getattr(connection, "vendor", "") == "postgresql" and hasattr(connection, "connection") and connection.connection:
                # The cursor was not closed: abandon the connection so PostgreSQL keeps it idle in transaction
                from analytics.apps import LEAKED_SESSIONS
                LEAKED_SESSIONS.append(connection.connection)
                connection.connection = None
                connection._active_cursors.clear()

        return response
