"""SQLite cache for Nominatim geocoding and Overpass POI queries."""

from __future__ import annotations

import json
import logging
import sqlite3
import time
from contextlib import contextmanager
from typing import Any, Generator

from ekkubo.config import CACHE_DB_PATH, CACHE_DIR, COORD_ROUND_DIGITS

logger = logging.getLogger(__name__)


def round_coord(value: float) -> float:
    return round(value, COORD_ROUND_DIGITS)


def make_geocode_key(query: str) -> str:
    return f"geocode:{query.strip().lower()}"


def make_poi_key(lat: float, lon: float, poi_type: str, radius_m: int) -> str:
    return f"poi:{poi_type}:{round_coord(lat)}:{round_coord(lon)}:{radius_m}"


class Cache:
    """TTL cache backed by SQLite."""

    def __init__(self, db_path: Path = CACHE_DB_PATH) -> None:
        CACHE_DIR.mkdir(parents=True, exist_ok=True)
        self.db_path = db_path
        self._init_db()

    def _init_db(self) -> None:
        with self._connect() as conn:
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS cache (
                    cache_key TEXT PRIMARY KEY,
                    payload TEXT NOT NULL,
                    created_at REAL NOT NULL,
                    ttl_seconds REAL NOT NULL
                )
                """
            )
            conn.commit()

    @contextmanager
    def _connect(self) -> Generator[sqlite3.Connection, None, None]:
        conn = sqlite3.connect(self.db_path)
        try:
            yield conn
        finally:
            conn.close()

    def get(self, key: str) -> Any | None:
        now = time.time()
        with self._connect() as conn:
            row = conn.execute(
                "SELECT payload, created_at, ttl_seconds FROM cache WHERE cache_key = ?",
                (key,),
            ).fetchone()
        if not row:
            logger.debug("cache MISS %s", key)
            return None
        payload, created_at, ttl = row
        if now - created_at > ttl:
            logger.debug("cache EXPIRED %s", key)
            self.delete(key)
            return None
        logger.info("cache HIT %s", key)
        return json.loads(payload)

    def set(self, key: str, value: Any, ttl_seconds: float) -> None:
        now = time.time()
        with self._connect() as conn:
            conn.execute(
                """
                INSERT OR REPLACE INTO cache (cache_key, payload, created_at, ttl_seconds)
                VALUES (?, ?, ?, ?)
                """,
                (key, json.dumps(value), now, ttl_seconds),
            )
            conn.commit()
        logger.debug("cache SET %s ttl=%ss", key, ttl_seconds)

    def delete(self, key: str) -> None:
        with self._connect() as conn:
            conn.execute("DELETE FROM cache WHERE cache_key = ?", (key,))
            conn.commit()
