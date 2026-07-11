"""Turn-by-turn routing via OSRM public demo server."""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Any

import requests

from ekkubo.config import OSRM_URL, USER_AGENT

logger = logging.getLogger(__name__)


@dataclass
class RouteStep:
    """One maneuver along the route."""

    distance_m: float
    duration_s: float
    maneuver_type: str
    modifier: str | None
    name: str | None
    lat: float
    lon: float
    instruction: str  # OSRM's default instruction text


@dataclass
class Route:
    distance_m: float
    duration_s: float
    steps: list[RouteStep] = field(default_factory=list)
    geometry: list[list[float]] = field(default_factory=list)


class RoutingError(Exception):
    """Raised when OSRM cannot compute a route."""


def _parse_step(step: dict[str, Any]) -> RouteStep:
    maneuver = step.get("maneuver", {})
    loc = maneuver.get("location", [0.0, 0.0])
    return RouteStep(
        distance_m=float(step.get("distance", 0)),
        duration_s=float(step.get("duration", 0)),
        maneuver_type=str(maneuver.get("type", "unknown")),
        modifier=maneuver.get("modifier"),
        name=step.get("name") or None,
        lon=float(loc[0]),
        lat=float(loc[1]),
        instruction=str(maneuver.get("instruction", "")),
    )


def get_route(
    origin_lat: float,
    origin_lon: float,
    dest_lat: float,
    dest_lon: float,
) -> Route:
    """
    Fetch a driving route from OSRM public demo server.

    Production note: replace OSRM_URL with a self-hosted instance loaded with
    Uganda's .osm.pbf extract from Geofabrik for reliability under load.
    """
    coords = f"{origin_lon},{origin_lat};{dest_lon},{dest_lat}"
    url = f"{OSRM_URL}/{coords}"
    params = {
        "steps": "true",
        "geometries": "geojson",
        "overview": "full",
        "annotations": "false",
    }
    headers = {"User-Agent": USER_AGENT}

    logger.info(
        "OSRM route: (%.4f, %.4f) -> (%.4f, %.4f)",
        origin_lat,
        origin_lon,
        dest_lat,
        dest_lon,
    )
    try:
        resp = requests.get(url, params=params, headers=headers, timeout=60)
        resp.raise_for_status()
        data = resp.json()
    except requests.RequestException as exc:
        raise RoutingError(f"OSRM request failed: {exc}") from exc

    if data.get("code") != "Ok" or not data.get("routes"):
        message = data.get("message", "No route found")
        raise RoutingError(f"OSRM: {message}")

    route_data = data["routes"][0]
    legs = route_data.get("legs", [])
    steps: list[RouteStep] = []
    for leg in legs:
        for step in leg.get("steps", []):
            steps.append(_parse_step(step))

    geometry: list[list[float]] = []
    geom = route_data.get("geometry", {})
    if geom.get("type") == "LineString":
        geometry = geom.get("coordinates", [])

    return Route(
        distance_m=float(route_data.get("distance", 0)),
        duration_s=float(route_data.get("duration", 0)),
        steps=steps,
        geometry=geometry,
    )
