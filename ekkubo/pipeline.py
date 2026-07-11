"""Orchestrates the full Ekkubo navigation pipeline."""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Callable

from ekkubo.cache import Cache
from ekkubo.geocoding import GeocodeResult, GeocodingError, geocode, geocode_best
from ekkubo.gemma_nav import (
    GemmaError,
    disambiguate_route,
    extract_search_term,
    suggest_clarifying_question,
)
from ekkubo.landmarks import OverpassError, pois_for_route_steps
from ekkubo.routing import Route, RoutingError, get_route
from ekkubo.speech import first_instruction_luganda, synthesize_speech

logger = logging.getLogger(__name__)

StatusCallback = Callable[[str], None]


class PipelineStatus(str, Enum):
    IDLE = "idle"
    GEOCODING = "geocoding"
    ROUTING = "routing"
    FINDING_LANDMARKS = "finding landmarks"
    GENERATING_INSTRUCTIONS = "generating instructions"
    GENERATING_SPEECH = "generating speech"
    DONE = "done"
    ERROR = "error"
    CLARIFY = "clarify"


@dataclass
class NavigationResult:
    status: PipelineStatus
    origin: GeocodeResult | None = None
    destination: GeocodeResult | None = None
    route: Route | None = None
    instructions: list[dict] = field(default_factory=list)
    audio_path: str | None = None
    message: str = ""
    clarifying_question: str | None = None


def _notify(cb: StatusCallback | None, status: str) -> None:
    logger.info("status: %s", status)
    if cb:
        cb(status)


def _geocode_with_retry(
    query: str,
    cache: Cache,
    raw_request: str,
    on_status: StatusCallback | None,
) -> GeocodeResult | None:
    _notify(on_status, PipelineStatus.GEOCODING.value)
    result = geocode_best(query, cache=cache)
    if result:
        return result

    # Retry with Gemma-cleaned search term
    try:
        cleaned = extract_search_term(raw_request)
        if cleaned.lower() != query.lower():
            logger.info("Retrying geocode with cleaned term: %r", cleaned)
            time.sleep(1)  # respect Nominatim rate limit between attempts
            result = geocode_best(cleaned, cache=cache)
            if result:
                return result
    except GemmaError as exc:
        logger.warning("Gemma search-term extraction failed: %s", exc)

    return None


def navigate(
    origin_query: str,
    destination_query: str,
    *,
    cache: Cache | None = None,
    on_status: StatusCallback | None = None,
    generate_audio: bool = True,
) -> NavigationResult:
    """
    Full live pipeline: geocode → route → POIs → Gemma instructions → TTS.

    All landmark data comes from live Nominatim/Overpass — nothing hardcoded.
    """
    cache = cache or Cache()
    raw_dest = destination_query

    try:
        origin = _geocode_with_retry(origin_query, cache, origin_query, on_status)
        if not origin:
            question = _safe_clarify(origin_query)
            return NavigationResult(
                status=PipelineStatus.CLARIFY,
                message=f"Could not find starting point: {origin_query}",
                clarifying_question=question,
            )

        dest = _geocode_with_retry(destination_query, cache, raw_dest, on_status)
        if not dest:
            question = _safe_clarify(raw_dest)
            return NavigationResult(
                status=PipelineStatus.CLARIFY,
                message=f"Could not find destination: {destination_query}",
                clarifying_question=question,
            )

        _notify(on_status, PipelineStatus.ROUTING.value)
        route = get_route(origin.lat, origin.lon, dest.lat, dest.lon)

        _notify(on_status, PipelineStatus.FINDING_LANDMARKS.value)
        try:
            pois_per_step = pois_for_route_steps(route.steps, cache=cache)
        except OverpassError as exc:
            logger.warning("Overpass failed, continuing with empty POI lists: %s", exc)
            pois_per_step = [[] for _ in route.steps]

        _notify(on_status, PipelineStatus.GENERATING_INSTRUCTIONS.value)
        instructions = disambiguate_route(route.steps, pois_per_step, rider_request=raw_dest)

        audio_path = None
        if generate_audio and instructions:
            _notify(on_status, PipelineStatus.GENERATING_SPEECH.value)
            script = first_instruction_luganda(instructions)
            if script:
                audio_path = str(synthesize_speech(script))

        _notify(on_status, PipelineStatus.DONE.value)
        return NavigationResult(
            status=PipelineStatus.DONE,
            origin=origin,
            destination=dest,
            route=route,
            instructions=instructions,
            audio_path=audio_path,
            message=f"Route ready: {len(instructions)} steps, "
            f"{route.distance_m / 1000:.1f} km, ~{route.duration_s / 60:.0f} min",
        )

    except RoutingError as exc:
        _notify(on_status, PipelineStatus.ERROR.value)
        return NavigationResult(
            status=PipelineStatus.ERROR,
            message=f"No route found: {exc}",
        )
    except GeocodingError as exc:
        _notify(on_status, PipelineStatus.ERROR.value)
        return NavigationResult(
            status=PipelineStatus.ERROR,
            message=str(exc),
        )
    except Exception as exc:
        logger.exception("Pipeline failed")
        _notify(on_status, PipelineStatus.ERROR.value)
        return NavigationResult(
            status=PipelineStatus.ERROR,
            message=f"Unexpected error: {exc}",
        )


def _safe_clarify(raw_request: str) -> str:
    try:
        return suggest_clarifying_question(raw_request)
    except GemmaError:
        return "Tukubuuza: oli wa ddala? (Can you describe the place more clearly?)"
