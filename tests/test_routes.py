#!/usr/bin/env python3
"""
End-to-end smoke test for Ekkubo using live OSM + Gemma API calls.

Usage:
  set GEMINI_API_KEY=your_key
  python -m tests.test_routes

Optional flags:
  --no-gemma   Skip Gemma disambiguation (tests geocode + route + POI only)
  --no-audio   Skip TTS generation
"""

from __future__ import annotations

import argparse
import logging
import sys

from ekkubo.cache import Cache
from ekkubo.geocoding import geocode_best
from ekkubo.gemma_nav import disambiguate_route
from ekkubo.landmarks import pois_for_route_steps
from ekkubo.routing import get_route
from ekkubo.speech import concatenate_instructions_luganda, synthesize_speech

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger(__name__)

# Real Kampala routes for verification
TEST_ROUTES = [
    ("Makerere University, Kampala", "Kisaasi, Kampala"),
    ("Wandegeya, Kampala", "Ntinda, Kampala"),
    ("Bugolobi, Kampala", "Najjanankumbi, Kampala"),
    ("Kampala City Centre", "Entebbe Road, Kampala"),
]


def run_route(
    origin_q: str,
    dest_q: str,
    cache: Cache,
    *,
    use_gemma: bool = True,
    use_audio: bool = False,
) -> bool:
    print("\n" + "=" * 60)
    print(f"ROUTE: {origin_q}  →  {dest_q}")
    print("=" * 60)

    origin = geocode_best(origin_q, cache=cache)
    if not origin:
        print(f"FAIL: could not geocode origin {origin_q!r}")
        return False
    print(f"Origin: {origin.display_name} ({origin.lat:.4f}, {origin.lon:.4f})")

    dest = geocode_best(dest_q, cache=cache)
    if not dest:
        print(f"FAIL: could not geocode destination {dest_q!r}")
        return False
    print(f"Dest:   {dest.display_name} ({dest.lat:.4f}, {dest.lon:.4f})")

    route = get_route(origin.lat, origin.lon, dest.lat, dest.lon)
    print(f"Route:  {route.distance_m / 1000:.1f} km, {len(route.steps)} steps, ~{route.duration_s / 60:.0f} min")

    pois = pois_for_route_steps(route.steps, cache=cache)
    poi_counts = [len(p) for p in pois]
    print(f"POIs:   {poi_counts} per step (total {sum(poi_counts)})")

    if use_gemma:
        instructions = disambiguate_route(route.steps, pois, rider_request=dest_q)
        for i, instr in enumerate(instructions[:5], 1):
            print(f"\n  Step {i} ({instr.get('distance_m')}m)")
            print(f"    Landmark: {instr.get('chosen_landmark')}")
            print(f"    LG: {instr.get('instruction_luganda')}")
            print(f"    EN: {instr.get('instruction_english')}")
        if len(instructions) > 5:
            print(f"  ... and {len(instructions) - 5} more steps")

        if use_audio and instructions:
            script = concatenate_instructions_luganda(instructions[:3])  # first 3 steps only for test
            path = synthesize_speech(script)
            print(f"\nTTS sample saved: {path}")
    else:
        print("(Gemma skipped — showing OSRM steps only)")
        for i, step in enumerate(route.steps[:5], 1):
            print(f"  Step {i}: {step.instruction} ({int(step.distance_m)}m)")

    print("\nOK")
    return True


def main() -> int:
    parser = argparse.ArgumentParser(description="Ekkubo live pipeline test")
    parser.add_argument("--no-gemma", action="store_true", help="Skip Gemma calls")
    parser.add_argument("--no-audio", action="store_true", help="Skip TTS")
    args = parser.parse_args()

    cache = Cache()
    passed = 0
    for origin, dest in TEST_ROUTES:
        try:
            if run_route(
                origin,
                dest,
                cache,
                use_gemma=not args.no_gemma,
                use_audio=not args.no_audio,
            ):
                passed += 1
        except Exception as exc:
            logger.exception("Route failed: %s → %s", origin, dest)
            print(f"FAIL: {exc}")

    print(f"\n{'=' * 60}")
    print(f"Results: {passed}/{len(TEST_ROUTES)} routes OK")
    return 0 if passed == len(TEST_ROUTES) else 1


if __name__ == "__main__":
    sys.exit(main())
