import sys
import types
import pytest
from django.db import connection
from django.test import Client
from django.urls import get_resolver, URLPattern, URLResolver


class TrackedCursor:
    """Wraps a database cursor to track whether close() was called."""

    def __init__(self, real_cursor):
        self._cursor = real_cursor
        self.closed = False

    def close(self):
        self.closed = True
        return self._cursor.close()

    def __enter__(self):
        if hasattr(self._cursor, "__enter__"):
            self._cursor.__enter__()
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        try:
            if hasattr(self._cursor, "__exit__"):
                self._cursor.__exit__(exc_type, exc_val, exc_tb)
        finally:
            self.closed = True

    def __getattr__(self, name):
        return getattr(self._cursor, name)


class TrackedConnection:
    """Mock connection for direct DB drivers like psycopg2."""

    def __init__(self):
        self.closed = False
        self.cursors = []

    def cursor(self):
        cur = TrackedCursor(types.SimpleNamespace(close=lambda: None, execute=lambda *a, **k: None, fetchall=lambda: []))
        self.cursors.append(cur)
        return cur

    def close(self):
        self.closed = True

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.close()


def get_all_parameter_free_get_endpoints():
    """Discover all parameter-free GET endpoints under /api/ dynamically."""
    resolver = get_resolver()
    endpoints = []

    def walk_patterns(patterns, prefix=""):
        for pattern in patterns:
            if isinstance(pattern, URLPattern):
                route = prefix + str(pattern.pattern)
                if not route.startswith("/"):
                    route = "/" + route
                # Only include parameter-free routes under /api/
                if "<" not in route and "(" not in route and route.startswith("/api/"):
                    endpoints.append(route)
            elif isinstance(pattern, URLResolver):
                walk_patterns(pattern.url_patterns, prefix + str(pattern.pattern))

    walk_patterns(resolver.url_patterns)
    return sorted(list(set(endpoints)))


@pytest.fixture
def cursor_tracker(monkeypatch):
    """Monkeypatches connection.cursor and psycopg2.connect to track cursor hygiene."""
    tracked_cursors = []
    tracked_conns = []
    orig_cursor = connection.cursor

    def spy_cursor(*args, **kwargs):
        real = orig_cursor(*args, **kwargs)
        wrapped = TrackedCursor(real)
        tracked_cursors.append(wrapped)
        return wrapped

    monkeypatch.setattr(connection, "cursor", spy_cursor)

    # Mock psycopg2.connect for raw psycopg2 tests on SQLite
    fake_psycopg2 = types.ModuleType("psycopg2")

    def spy_connect(*args, **kwargs):
        conn = TrackedConnection()
        tracked_conns.append(conn)
        return conn

    fake_psycopg2.connect = spy_connect
    monkeypatch.setitem(sys.modules, "psycopg2", fake_psycopg2)

    return {
        "cursors": tracked_cursors,
        "conns": tracked_conns,
    }


@pytest.mark.django_db
def test_all_api_endpoints_cursor_hygiene(client, cursor_tracker):
    """
    Every parameter-free GET endpoint under /api/ must close all opened cursors.
    Fails if any endpoint opens a cursor without closing it or using a context manager.
    """
    endpoints = get_all_parameter_free_get_endpoints()
    assert len(endpoints) > 0, "No API endpoints discovered"

    for endpoint in endpoints:
        cursor_tracker["cursors"].clear()
        cursor_tracker["conns"].clear()

        client.get(endpoint)

        for cur in cursor_tracker["cursors"]:
            assert cur.closed, (
                f"Connection leak detected in {endpoint}: "
                f"cursor opened on connection was never closed!"
            )

        for conn in cursor_tracker["conns"]:
            assert conn.closed, (
                f"Direct DB connection leak detected in {endpoint}: "
                f"psycopg2 connection was never closed!"
            )


@pytest.mark.django_db
def test_fake_fix_unreachable_close_fails(cursor_tracker):
    """
    Regression assertion: placing cursor.close() after 'return' leaves the cursor unclosed,
    which must fail the hygiene check.
    """
    def leaky_view_with_unreachable_close():
        cursor = connection.cursor()
        cursor.execute("SELECT 1")
        return {"status": "ok"}
        cursor.close()  # Unreachable!

    cursor_tracker["cursors"].clear()
    leaky_view_with_unreachable_close()

    assert len(cursor_tracker["cursors"]) == 1
    unclosed = [c for c in cursor_tracker["cursors"] if not c.closed]
    assert len(unclosed) == 1, "Expected unreachable cursor.close() to fail closure assertion!"


@pytest.mark.django_db
def test_context_manager_fix_passes(cursor_tracker):
    """
    Regression assertion: wrapping query execution in 'with connection.cursor() as cursor:'
    properly closes the cursor upon exit.
    """
    def fixed_view_with_context_manager():
        with connection.cursor() as cursor:
            cursor.execute("SELECT 1")
        return {"status": "ok"}

    cursor_tracker["cursors"].clear()
    fixed_view_with_context_manager()

    assert len(cursor_tracker["cursors"]) == 1
    assert cursor_tracker["cursors"][0].closed is True
