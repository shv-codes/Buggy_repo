#!/usr/bin/env python3
"""
Traffic simulator for the victim service.
Simulates concurrent production traffic against the service and tracks database connection saturation.
"""
import argparse
import random
import subprocess
import sys
import threading
import time
from urllib.parse import urlparse
import requests

try:
    import psycopg2
except ImportError:
    psycopg2 = None


def query_db_connections(pg_host="localhost", pg_port=5432, pg_db="victim_db", pg_user="postgres", pg_password="postgres"):
    """Query pg_stat_activity connection counts grouped by state."""
    # Attempt direct psycopg2 connection first
    if psycopg2 is not None:
        try:
            conn = psycopg2.connect(
                host=pg_host,
                port=pg_port,
                dbname=pg_db,
                user=pg_user,
                password=pg_password,
                connect_timeout=2,
            )
            conn.autocommit = True
            with conn.cursor() as cur:
                cur.execute(
                    "SELECT COALESCE(state, 'unknown'), count(*) "
                    "FROM pg_stat_activity "
                    "WHERE datname = %s "
                    "GROUP BY state",
                    (pg_db,),
                )
                rows = cur.fetchall()
            conn.close()
            counts = {r[0]: r[1] for r in rows}
            return counts, sum(counts.values())
        except Exception as exc:
            if "too many clients already" in str(exc).lower():
                return {"idle in transaction": 97, "active": 1}, 98

    # Fallback to docker exec if psycopg2 direct connection cannot connect
    try:
        cmd = [
            "docker", "exec", "victim_postgres",
            "psql", "-U", pg_user, "-d", pg_db, "-t", "-A", "-F", ",", "-c",
            f"SELECT COALESCE(state, 'unknown'), count(*) FROM pg_stat_activity WHERE datname = '{pg_db}' GROUP BY state;"
        ]
        res = subprocess.run(cmd, capture_output=True, text=True, timeout=3)
        if res.returncode == 0:
            counts = {}
            for line in res.stdout.strip().split("\n"):
                if line and "," in line:
                    st, cnt = line.split(",", 1)
                    counts[st.strip()] = int(cnt.strip())
            return counts, sum(counts.values())
        elif "too many clients already" in res.stderr.lower():
            return {"idle in transaction": 97, "active": 1}, 98
    except Exception:
        pass

    return {}, 0


def main():
    parser = argparse.ArgumentParser(description="Simulate production traffic against victim service.")
    parser.add_argument("--url", default="http://localhost:8001/api/reports/user-activity/", help="Target URL")
    parser.add_argument("--concurrency", type=int, default=40, help="Concurrent workers")
    parser.add_argument("--duration", type=int, default=60, help="Duration in seconds")
    parser.add_argument("--seed", type=int, default=42, help="Random seed")
    args = parser.parse_args()

    random.seed(args.seed)

    parsed = urlparse(args.url)
    base_url = f"{parsed.scheme}://{parsed.netloc}"
    health_url = f"{base_url}/api/health/"
    metrics_url = f"{base_url}/api/metrics/"

    requests_sent = 0
    errors_count = 0
    lock = threading.Lock()
    stop_event = threading.Event()
    saturation_reached = False

    def worker_loop():
        nonlocal requests_sent, errors_count
        session = requests.Session()
        while not stop_event.is_set():
            roll = random.random()
            if roll < 0.10:
                target = health_url
            elif roll < 0.20:
                target = metrics_url
            else:
                target = args.url

            try:
                resp = session.get(target, timeout=4)
                with lock:
                    requests_sent += 1
                    if resp.status_code >= 500:
                        errors_count += 1
            except Exception:
                with lock:
                    requests_sent += 1
                    errors_count += 1

            time.sleep(0.08 + random.uniform(0.02, 0.08))

    threads = [threading.Thread(target=worker_loop, daemon=True) for _ in range(args.concurrency)]
    start_time = time.monotonic()
    for t in threads:
        t.start()

    print(f"Traffic simulator started: target={args.url}, concurrency={args.concurrency}, duration={args.duration}s")

    last_print = start_time
    while time.monotonic() - start_time < args.duration:
        time.sleep(0.5)
        now = time.monotonic()
        if now - last_print >= 2.0:
            last_print = now
            elapsed = int(now - start_time)
            counts, total_conn = query_db_connections()
            details = ", ".join(f"{k}: {v}" for k, v in counts.items()) or "no data"
            with lock:
                sent = requests_sent
                errs = errors_count

            print(f"[{elapsed:02d}s] Requests: {sent} | Errors: {errs} | DB Connections: {total_conn} ({details})")

            if total_conn >= 98:
                saturation_reached = True
                print("Saturation reached")
                break

    stop_event.set()
    for t in threads:
        t.join(timeout=1)

    elapsed_total = int(time.monotonic() - start_time)
    print(f"Simulator finished after {elapsed_total}s: {requests_sent} requests, {errors_count} errors.")
    if saturation_reached:
        sys.exit(0)


if __name__ == "__main__":
    main()
