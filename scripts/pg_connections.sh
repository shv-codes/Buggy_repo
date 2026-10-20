#!/usr/bin/env bash
# prints pg_stat_activity counts grouped by state

PG_CONTAINER="${PG_CONTAINER:-victim_postgres}"
PG_DB="${PG_DB:-victim_db}"
PG_USER="${PG_USER:-postgres}"

docker exec "$PG_CONTAINER" psql -U "$PG_USER" -d "$PG_DB" -c "
SELECT COALESCE(state, 'unknown') AS state, count(*) AS count
FROM pg_stat_activity
WHERE datname = '$PG_DB'
GROUP BY state
ORDER BY count DESC;
"
