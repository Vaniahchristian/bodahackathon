"""POI lookup near route steps via Overpass API."""

from __future__ import annotations

import logging
import threading
import time
from dataclasses import dataclass, field
from typing import Any

import requests

from ekkubo.cache import Cache, make_poi_key
from ekkubo.config import (
    OVERPASS_MIN_INTERVAL_S,
    OVERPASS_URL,
    POI_SEARCH_RADIUS_M,
    POI_TTL_S,
    USER_AGENT,
)

logger = logging.getLogger(__name__)

_rate_lock = threading.Lock()
_last_request_at = 0.0

# Amenity / shop tags we care about for Kampala boda navigation
POI_FILTERS = [
    'node["amenity"="fuel"]',
    'node["amenity"="place_of_worship"]',
    'node["amenity"="taxi"]',
    'node["amenity"="marketplace"]',
    'node["shop"]',
    'way["amenity"="fuel"]',
    'way["amenity"="place_of_worship"]',
    'way["amenity"="taxi"]',
    'way["amenity"="marketplace"]',
    'way["shop"]',
]


@dataclass
class POI:
    osm_id: int
    osm_type: str
    name: str | None
    amenity: str | None
    shop: str | None
    lat: float
    lon: float
    tags: dict[str, str] = field(default_factory=dict)

    @property
    def category(self) -> str:
        if self.amenity:
            return self.amenity
        if self.shop:
            return f"shop:{self.shop}"
        return "unknown"

    @property
    def label(self) -> str:
        if self.name:
            return self.name
        return self.category.replace("_", " ").title()


class OverpassError(Exception):
    """Raised when Overpass query fails."""


def _respect_rate_limit() -> None:
    global _last_request_at
    with _rate_lock:
        elapsed = time.time() - _last_request_at
        if elapsed < OVERPASS_MIN_INTERVAL_S:
            time.sleep(OVERPASS_MIN_INTERVAL_S - elapsed)
        _last_request_at = time.time()


def _build_overpass_query(lat: float, lon: float, radius_m: int) -> str:
    union = "\n".join(
        f"  {f}(around:{radius_m},{lat},{lon});" for f in POI_FILTERS
    )
    return f"""
[out:json][timeout:25];
(
{union}
);
out center tags;
"""


def _parse_element(element: dict[str, Any]) -> POI | None:
    tags = element.get("tags", {})
    if element["type"] == "node":
        lat, lon = element.get("lat"), element.get("lon")
    else:
        center = element.get("center", {})
        lat, lon = center.get("lat"), center.get("lon")
    if lat is None or lon is None:
        return None
    return POI(
        osm_id=int(element["id"]),
        osm_type=str(element["type"]),
        name=tags.get("name"),
        amenity=tags.get("amenity"),
        shop=tags.get("shop"),
        lat=float(lat),
        lon=float(lon),
        tags=tags,
    )


def query_pois_near(
    lat: float,
    lon: float,
    cache: Cache | None = None,
    *,
    radius_m: int = POI_SEARCH_RADIUS_M,
    use_cache: bool = True,
) -> list[POI]:
    """Query real POIs within radius of a coordinate."""
    cache = cache or Cache()
    key = make_poi_key(lat, lon, "all", radius_m)

    if use_cache:
        cached = cache.get(key)
        if cached is not None:
            return [POI(**item) for item in cached]

    query = _build_overpass_query(lat, lon, radius_m)
    headers = {"User-Agent": USER_AGENT}

    _respect_rate_limit()
    logger.info("Overpass POI query at (%.4f, %.4f) r=%dm", lat, lon, radius_m)
    try:
        resp = requests.post(
            OVERPASS_URL,
            data={"data": query},
            headers=headers,
            timeout=35,
        )
        if resp.status_code == 429:
            raise OverpassError("Overpass rate limit hit")
        resp.raise_for_status()
        data = resp.json()
    except requests.RequestException as exc:
        raise OverpassError(f"Overpass request failed: {exc}") from exc

    pois: list[POI] = []
    for element in data.get("elements", []):
        poi = _parse_element(element)
        if poi:
            pois.append(poi)

    if use_cache:
        cache.set(
            key,
            [
                {
                    "osm_id": p.osm_id,
                    "osm_type": p.osm_type,
                    "name": p.name,
                    "amenity": p.amenity,
                    "shop": p.shop,
                    "lat": p.lat,
                    "lon": p.lon,
                    "tags": p.tags,
                }
                for p in pois
            ],
            POI_TTL_S,
        )

    logger.info("Found %d POIs near (%.4f, %.4f)", len(pois), lat, lon)
    return pois


def pois_for_route_steps(
    steps: list,
    cache: Cache | None = None,
    *,
    radius_m: int = POI_SEARCH_RADIUS_M,
) -> list[list[POI]]:
    """Fetch POI candidates for each route step maneuver point."""
    cache = cache or Cache()
    return [
        query_pois_near(step.lat, step.lon, cache=cache, radius_m=radius_m)
        for step in steps
    ]
