"""Geocoding via Nominatim with rate limiting and caching."""

from __future__ import annotations

import logging
import threading
import time
from dataclasses import dataclass
from typing import Any

import requests

from ekkubo.cache import Cache, make_geocode_key
from ekkubo.config import (
    GEOCODE_TTL_S,
    KAMPALA_VIEWBOX,
    NOMINATIM_MIN_INTERVAL_S,
    NOMINATIM_URL,
    USER_AGENT,
)

logger = logging.getLogger(__name__)

_rate_lock = threading.Lock()
_last_request_at = 0.0


@dataclass
class GeocodeResult:
    display_name: str
    lat: float
    lon: float
    importance: float
    raw: dict[str, Any]


class GeocodingError(Exception):
    """Raised when geocoding fails."""


def _respect_rate_limit() -> None:
    global _last_request_at
    with _rate_lock:
        elapsed = time.time() - _last_request_at
        if elapsed < NOMINATIM_MIN_INTERVAL_S:
            time.sleep(NOMINATIM_MIN_INTERVAL_S - elapsed)
        _last_request_at = time.time()


def _nominatim_search(query: str, limit: int = 5) -> list[dict[str, Any]]:
    south, north, west, east = KAMPALA_VIEWBOX
    params = {
        "q": query,
        "format": "json",
        "limit": limit,
        "viewbox": f"{west},{north},{east},{south}",
        "bounded": 1,
        "addressdetails": 1,
    }
    headers = {"User-Agent": USER_AGENT}

    _respect_rate_limit()
    logger.info("Nominatim search: %r", query)
    resp = requests.get(NOMINATIM_URL, params=params, headers=headers, timeout=30)
    if resp.status_code == 429:
        raise GeocodingError("Nominatim rate limit hit — retry after backoff")
    resp.raise_for_status()
    return resp.json()


def geocode(
    query: str,
    cache: Cache | None = None,
    *,
    use_cache: bool = True,
) -> list[GeocodeResult]:
    """Geocode a place name to coordinates, preferring Kampala area."""
    cache = cache or Cache()
    key = make_geocode_key(query)

    if use_cache:
        cached = cache.get(key)
        if cached is not None:
            return [GeocodeResult(**item) for item in cached]

    try:
        data = _nominatim_search(query)
    except requests.RequestException as exc:
        raise GeocodingError(f"Nominatim request failed: {exc}") from exc

    results = [
        GeocodeResult(
            display_name=item.get("display_name", query),
            lat=float(item["lat"]),
            lon=float(item["lon"]),
            importance=float(item.get("importance", 0)),
            raw=item,
        )
        for item in data
    ]

    if use_cache and results:
        cache.set(
            key,
            [
                {
                    "display_name": r.display_name,
                    "lat": r.lat,
                    "lon": r.lon,
                    "importance": r.importance,
                    "raw": r.raw,
                }
                for r in results
            ],
            GEOCODE_TTL_S,
        )

    return results


def geocode_best(
    query: str,
    cache: Cache | None = None,
) -> GeocodeResult | None:
    """Return the highest-importance geocode result, or None."""
    results = geocode(query, cache=cache)
    if not results:
        return None
    return max(results, key=lambda r: r.importance)
