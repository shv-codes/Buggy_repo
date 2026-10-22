# victim-service (Buggy_repo)

> ⚠️ **WARNING**: This repo contains intentional bugs for testing AutoSRE. Do not use in production.

A small Django 4.2 + PostgreSQL 15 service called "victim-service" designed as a target victim repository for **AutoSRE** (an AI agent that monitors PostgreSQL connections, detects leaks, isolates culprit commits using GitPython, patches the code via LLM, validates in an isolated Docker sandbox, and creates draft pull requests).

---

## Architecture & Endpoints

The service exposes the following API endpoints under `/api/`:
- `GET /api/health/`: Fast health check endpoint (`views.health_check`).
- `GET /api/metrics/`: High-level metrics summary computed via Django ORM (`views.metrics_summary`).
- `GET /api/reports/user-activity/`: High-performance reporting endpoint utilizing raw SQL queries (`views.user_activity_report`).

---

## The Intentional Bug: PostgreSQL Connection Leak

### Where It Is
The leak is located in [`analytics/views.py`](analytics/views.py) inside `user_activity_report`:

```python
def user_activity_report(request):
    """Raw-SQL user activity report endpoint."""
    cursor = connection.cursor()
    cursor.execute("SELECT 101 AS user_id, 'login_session' AS event, CURRENT_TIMESTAMP AS ts")
    rows = cursor.fetchall()
    data = [{"user_id": r[0], "event": r[1], "ts": str(r[2])} for r in rows]
    return JsonResponse({"status": "ok", "data": data})
```

### Why the Leak Holds Connections
When `cursor = connection.cursor()` is invoked on a raw database connection, PostgreSQL begins a database transaction. Because the cursor is neither closed (`cursor.close()`) nor managed by a context manager (`with connection.cursor() as cursor:`), the database transaction remains uncommitted and the session is held open in PostgreSQL in state **`idle in transaction`**.

Under threaded Gunicorn (`--workers 1 --threads 120`) with persistent connections (`CONN_MAX_AGE=None`), requests that abandon open cursors leave connections pinned in the transaction pool. As concurrent incoming requests arrive, PostgreSQL rapidly accumulates stuck sessions until it reaches `max_connections` (100). Once 98 connections are exhausted, all subsequent connection attempts fail with:
```
FATAL: sorry, too many clients already
```

### The Correct Fix
Wrap raw cursor acquisition in a Python context manager:
```python
def user_activity_report(request):
    """Raw-SQL user activity report endpoint."""
    with connection.cursor() as cursor:
        cursor.execute("SELECT 101 AS user_id, 'login_session' AS event, CURRENT_TIMESTAMP AS ts")
        rows = cursor.fetchall()
        data = [{"user_id": r[0], "event": r[1], "ts": str(r[2])} for r in rows]
    return JsonResponse({"status": "ok", "data": data})
```

---

## Quickstart

### 1. Run the Service
Start PostgreSQL and the victim service via Docker Compose:
```bash
docker compose up -d --build
```

### 2. Simulate Production Traffic
Run the deterministic traffic simulator (concurrency: 40, duration: 60s):
```bash
python traffic_simulator.py --concurrency 40 --duration 60
```
The simulator will hit `/api/reports/user-activity/` while lightly probing `/api/health/` and `/api/metrics/`. Once connection saturation reaches 98/100, it prints `"Saturation reached"` and terminates.

### 3. Inspect Live Database Connections
Monitor connection count grouped by state:
```bash
./scripts/pg_connections.sh
```
Or directly inspect `pg_stat_activity`:
```bash
docker exec -it victim_postgres psql -U postgres -d victim_db -c "
SELECT COALESCE(state, 'unknown') AS state, count(*) 
FROM pg_stat_activity 
WHERE datname = 'victim_db' 
GROUP BY state;"
```

### 4. Running Tests (Offline & SQLite)
Tests run completely without PostgreSQL and without network:
```bash
pytest
```
- On healthy baseline (`healthy-baseline` tag): all 5 tests pass.
- On `main` (`leak-introduced` tag): all tests pass except `test_leak_regression.py`, which flags the unclosed cursor.

---

## Commit History

| Commit | Author | Message | State |
|---|---|---|---|
| `b838f46` | Shivansh | Initial Django project with health endpoint | Clean |
| `be75add` | Ananya | Add UserMetric model and metrics summary endpoint | Clean |
| `d931bda` | Shivansh | Add tests, Docker setup and JSON request logging (`healthy-baseline`) | Clean |
| `b686f3b` | Meera | Add traffic simulator and pg connection script | Clean |
| `ffd2d90` | Charlie Contributor | Add raw-sql user activity report (`leak-introduced`) | **Leaky** |
| `55cf869` | Ananya | Update README with setup instructions | **Leaky** |

---

## Scenario Branches

Additional scenario branches demonstrate different patterns of database leaks caught by the generic cursor-hygiene regression test:

1. **`scenario/try-without-finally`**:
   - Commit: *"Add CSV export for activity data"*
   - Endpoint: `GET /api/reports/export-csv/`
   - Bug: Cursor opened in `try` block with no `finally` clause, leaving cursor unclosed on successful requests.

2. **`scenario/early-return`**:
   - Commit: *"Add top users report"*
   - Endpoint: `GET /api/reports/top-users/`
   - Bug: Cursor opened and closed at end of function, but an early `return` when no rows are found bypasses `cursor.close()`.

3. **`scenario/raw-psycopg2`**:
   - Commit: *"Add direct DB health probe"*
   - Endpoint: `GET /api/metrics/db-probe/`
   - Bug: Raw `psycopg2.connect(...)` opened directly without `close()` or context management.

---

## Resetting the Environment

To reset everything back to a clean state:
```bash
git checkout main
docker compose down -v
```
