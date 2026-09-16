"""City history collection, bounded online repairs and durable backfill jobs."""

from __future__ import annotations

import asyncio
from contextlib import contextmanager
from datetime import date, datetime, timedelta, timezone
import fcntl
import hashlib
import json
import math
from pathlib import Path
import sqlite3
import time

import structlog

from app.db.repositories.weather_repo import WeatherRepository
from app.external_apis.openmeteo_client import OpenMeteoClient
from app.utils.weather_time import OPEN_METEO_SOURCE, weather_query_time

logger = structlog.get_logger()
HOUR = timedelta(hours=1)


def grid_point(lat, lon):
    return round(lat * 4) / 4, round(lon * 4) / 4


def valid_height(value):
    return isinstance(value, (float, int)) and math.isfinite(value) and value >= 0


def expected_hours(start, end):
    start, end = weather_query_time(start), weather_query_time(end)
    hour = start.replace(minute=0, second=0, microsecond=0)
    if hour < start:
        hour += HOUR
    while hour <= end:
        yield hour
        hour += HOUR


def coverage(rows, start, end):
    expected = set(expected_hours(start, end))
    valid = {
        weather_query_time(row.time) for row in rows
        if valid_height(row.boundary_layer_height)
        and row.data_source == OPEN_METEO_SOURCE
    } & expected
    missing = expected - valid
    return {
        "expected_hours": len(expected),
        "valid_hours": len(valid),
        "missing_hours": len(missing),
        "missing_rate": len(missing) / len(expected) if expected else 0,
        "valid_timestamps": sorted(hour.isoformat() for hour in valid),
    }


class HistoryJobs:
    """Small local durable queue shared by web and its single worker."""

    def __init__(self, root: Path):
        self.root = root
        root.mkdir(parents=True, exist_ok=True)
        self.path = root / "jobs.sqlite3"
        with self.connect() as conn:
            conn.execute("""CREATE TABLE IF NOT EXISTS jobs (
                id TEXT PRIMARY KEY, payload TEXT NOT NULL, state TEXT NOT NULL,
                cursor INTEGER NOT NULL DEFAULT 0, total INTEGER NOT NULL,
                failed INTEGER NOT NULL DEFAULT 0, updated REAL NOT NULL,
                error TEXT)""")

    @contextmanager
    def connect(self):
        conn = sqlite3.connect(self.path, timeout=5)
        conn.row_factory = sqlite3.Row
        try:
            with conn:
                yield conn
        finally:
            conn.close()

    def submit(self, points, start: date, end: date):
        if not points or len(points) > 100 or start > end or (end - start).days >= 366:
            raise ValueError("History jobs require 1 to 366 days")
        payload = json.dumps({"points": points, "start": start.isoformat(), "end": end.isoformat()}, sort_keys=True)
        job_id = hashlib.sha256(payload.encode()).hexdigest()[:24]
        chunks = len(points) * math.ceil(((end - start).days + 1) / 30)
        with self.connect() as conn:
            conn.execute("INSERT OR IGNORE INTO jobs(id,payload,state,total,updated) VALUES (?,?, 'pending',?,?)",
                         (job_id, payload, chunks, time.time()))
            # A repeated query can retry unavailable data, but never hammer the provider.
            conn.execute("UPDATE jobs SET state='pending',cursor=0,failed=0,error=NULL,updated=? "
                         "WHERE id=? AND state='partial' AND updated < ?",
                         (time.time(), job_id, time.time() - 3600))
        return self.get(job_id)

    def get(self, job_id):
        with self.connect() as conn:
            row = conn.execute("SELECT id,state,cursor,total,failed,error FROM jobs WHERE id=?", (job_id,)).fetchone()
        return dict(row) if row else None

    def pending(self):
        with self.connect() as conn:
            return [dict(row) for row in conn.execute(
                "SELECT * FROM jobs WHERE state IN ('pending','running') ORDER BY updated LIMIT 4")]

    def checkpoint(self, job_id, cursor, failed, total, error=None):
        state = ("partial" if failed else "complete") if cursor == total else "running"
        with self.connect() as conn:
            conn.execute("UPDATE jobs SET state=?,cursor=?,failed=?,updated=?,error=? WHERE id=?",
                         (state, cursor, failed, time.time(), error, job_id))


class WeatherHistoryService:
    def __init__(self, config, *, project_id, root=None, repo=None, client=None):
        self.config = config
        self.project_id = project_id
        if root is None:
            from app.utils.path_config import get_data_registry
            root = get_data_registry() / "weather_history" / project_id
        self.jobs = HistoryJobs(Path(root))
        self.repo = repo or WeatherRepository()
        self.client = client or OpenMeteoClient()

    def points(self):
        return [point.model_dump() for point in self.config.points]

    def resolve(self, city):
        key = city.strip().removesuffix("市")
        return next((p for p in self.config.points if p.city.removesuffix("市") == key), None)

    async def repair(self, lat, lon, start, end):
        """Fetch only UTC days with missing/invalid boundary-layer values."""
        rows = await self.repo.get_weather_data(lat, lon, start, end)
        valid = {weather_query_time(row.time) for row in rows
                 if valid_height(row.boundary_layer_height) and row.data_source == OPEN_METEO_SOURCE}
        days = sorted({hour.date() for hour in expected_hours(start, end) if hour not in valid})
        ranges = []
        for day in days:
            if ranges and day == ranges[-1][1] + timedelta(days=1):
                ranges[-1][1] = day
            else:
                ranges.append([day, day])
        for first, last in ranges:
            data = await self.client.fetch_era5_data(lat, lon, first.isoformat(), last.isoformat())
            # Keep validated cached values when the provider returns a partial day.
            await self.repo.save_era5_data(lat, lon, data, preserve_valid=True)
            await asyncio.sleep(0.25)
        rows = await self.repo.get_weather_data(lat, lon, start, end)
        return coverage(rows, start, end)

    def submit(self, points, start, end):
        # Today belongs to the forecast tool. Archive requests stop at yesterday UTC.
        end = min(weather_query_time(end).date(), datetime.now(timezone.utc).date() - timedelta(days=1))
        start = weather_query_time(start).date()
        if start > end:
            return None
        return self.jobs.submit(points, start, end)

    def schedule_collection(self):
        end = datetime.now(timezone.utc).date() - timedelta(days=1)
        marker = self.jobs.root / "bootstrap.json"
        fingerprint = hashlib.sha256(json.dumps(self.points(), sort_keys=True).encode()).hexdigest()
        previous = json.loads(marker.read_text()) if marker.exists() else {}
        if previous.get("points") != fingerprint:
            previous = {"points": fingerprint, "start": (end - timedelta(days=self.config.bootstrap_days - 1)).isoformat(), "end": end.isoformat()}
            temporary = marker.with_suffix(".tmp")
            temporary.write_text(json.dumps(previous))
            temporary.replace(marker)
        self.jobs.submit(self.points(), date.fromisoformat(previous["start"]), date.fromisoformat(previous["end"]))
        self.jobs.submit(self.points(), end - timedelta(days=self.config.lookback_days - 1), end)

    async def run_pending(self, max_chunks=60):
        # OS locking survives cancellation and releases automatically after a crash.
        with (self.jobs.root / "worker.lock").open("a") as lock:
            try:
                fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
            except BlockingIOError:
                return
            processed = 0
            for job in self.jobs.pending():
                payload = json.loads(job["payload"])
                tasks = []
                for point in payload["points"]:
                    first = date.fromisoformat(payload["start"])
                    end = date.fromisoformat(payload["end"])
                    while first <= end:
                        last = min(first + timedelta(days=29), end)
                        tasks.append((point, first, last))
                        first = last + timedelta(days=1)
                failed = job["failed"]
                for index in range(job["cursor"], len(tasks)):
                    point, first, last = tasks[index]
                    error = None
                    try:
                        lat, lon = grid_point(point["lat"], point["lon"])
                        result = await self.repair(lat, lon,
                            datetime.combine(first, datetime.min.time(), timezone.utc),
                            datetime.combine(last, datetime.min.time(), timezone.utc) + 23 * HOUR)
                        if result["missing_hours"]:
                            failed += 1
                            error = f'{point["city"]}: {result["missing_hours"]} missing hours'
                    except Exception as exc:
                        failed += 1
                        error = f'{point["city"]}: {type(exc).__name__}'
                        logger.warning("weather_history_chunk_failed", city=point["city"], error=str(exc))
                    self.jobs.checkpoint(job["id"], index + 1, failed, len(tasks), error)
                    processed += 1
                    if processed >= max_chunks:
                        return


def configured_history_service():
    from config.settings import settings
    from app.project_config import load_project_context
    backend = load_project_context(settings.project_id).manifest.backend
    if backend.weather_history is None or not backend.fetchers_enabled:
        return None
    return WeatherHistoryService(backend.weather_history, project_id=settings.project_id)
