"""Gemma 4 integration for geocoding cleanup, landmark disambiguation, and instruction generation."""

from __future__ import annotations

import json
import logging
import re
from typing import Any

import requests

from ekkubo.config import GEMINI_API_KEY, GEMINI_API_URL
from ekkubo.landmarks import POI
from ekkubo.routing import RouteStep

logger = logging.getLogger(__name__)


class GemmaError(Exception):
    """Raised when Gemma API call fails or returns unusable output."""


SYSTEM_INSTRUCTION = """You are Ekkubo, an audio navigation assistant for boda boda (motorcycle taxi)
riders in Kampala, Uganda. Riders speak informally, often mixing Luganda and English.

Rules:
- Keep spoken Luganda instructions SHORT (one sentence, max ~15 words) — riders hear this while moving.
- Never invent landmarks not in the candidate list.
- Prefer named POIs (fuel stations, mosques, markets, taxi stages) over generic descriptions.
- If no good landmark exists, use street name or maneuver direction only.
- Always respond with valid JSON only, no markdown fences."""


def _call_gemma(user_prompt: str, *, temperature: float = 0.3) -> str:
    if not GEMINI_API_KEY:
        raise GemmaError(
            "GEMINI_API_KEY or GOOGLE_API_KEY not set. "
            "Get one at https://aistudio.google.com/apikey"
        )

    payload = {
        "systemInstruction": {"parts": [{"text": SYSTEM_INSTRUCTION}]},
        "contents": [{"role": "user", "parts": [{"text": user_prompt}]}],
        "generationConfig": {
            "temperature": temperature,
            "responseMimeType": "application/json",
        },
    }
    url = f"{GEMINI_API_URL}?key={GEMINI_API_KEY}"
    try:
        resp = requests.post(url, json=payload, timeout=90)
        resp.raise_for_status()
        data = resp.json()
    except requests.RequestException as exc:
        raise GemmaError(f"Gemma API request failed: {exc}") from exc

    try:
        return data["candidates"][0]["content"]["parts"][0]["text"]
    except (KeyError, IndexError) as exc:
        raise GemmaError(f"Unexpected Gemma response shape: {data}") from exc


def _parse_json(text: str) -> Any:
    text = text.strip()
    # Strip markdown fences if model ignores instruction
    text = re.sub(r"^```(?:json)?\s*", "", text)
    text = re.sub(r"\s*```$", "", text)
    return json.loads(text)


def extract_search_term(raw_request: str) -> str:
    """Use Gemma to clean informal destination phrasing before geocoding retry."""
    prompt = f"""The rider said this destination (possibly Luganda/English mix):
"{raw_request}"

Extract a clean place name suitable for OpenStreetMap geocoding in Kampala, Uganda.
Return JSON: {{"search_term": "...", "confidence": "high|medium|low"}}"""
    raw = _call_gemma(prompt)
    data = _parse_json(raw)
    return str(data.get("search_term", raw_request)).strip()


def suggest_clarifying_question(raw_request: str) -> str:
    """When geocoding fails, ask the rider a helpful follow-up."""
    prompt = f"""Geocoding failed for this rider request in Kampala:
"{raw_request}"

Suggest ONE short clarifying question to ask the rider (Luganda + English mix is fine).
Return JSON: {{"question_luganda": "...", "question_english": "..."}}"""
    raw = _call_gemma(prompt, temperature=0.5)
    data = _parse_json(raw)
    lg = data.get("question_luganda", "")
    en = data.get("question_english", "")
    return f"{lg}\n({en})" if lg and en else lg or en or "Tukubuuza: oli wa? (Where exactly are you going?)"


def _poi_to_dict(poi: POI) -> dict[str, Any]:
    return {
        "name": poi.name,
        "category": poi.category,
        "label": poi.label,
        "lat": poi.lat,
        "lon": poi.lon,
    }


def disambiguate_step(
    step: RouteStep,
    candidate_pois: list[POI],
    rider_phrasing_style: str = "",
) -> dict[str, Any]:
    """
    Pick the best landmark and generate bilingual spoken instructions for one step.

    Returns dict with keys:
      distance_m, maneuver, chosen_landmark, instruction_luganda, instruction_english
    """
    poi_list = [_poi_to_dict(p) for p in candidate_pois[:15]]
    prompt = f"""Route step for a boda boda rider in Kampala:
- Distance to maneuver: {int(step.distance_m)} meters
- Maneuver type: {step.maneuver_type}
- Modifier: {step.modifier or "none"}
- Street name: {step.name or "unknown"}
- OSRM instruction: {step.instruction}
- Rider's original style/phrasing: "{rider_phrasing_style or "informal Kampala mix"}"

Nearby POI candidates from OpenStreetMap (ONLY choose from this list or null):
{json.dumps(poi_list, ensure_ascii=False)}

Tasks:
a) Pick the most locally-recognizable landmark from candidates (prefer named fuel, mosque, market, taxi stage)
b) If none suitable, set chosen_landmark to null and use street/direction only
c) Write SHORT spoken Luganda instruction + English display version

Return JSON:
{{
  "distance_m": {int(step.distance_m)},
  "maneuver": "{step.maneuver_type}",
  "chosen_landmark": "name or null",
  "instruction_luganda": "...",
  "instruction_english": "..."
}}"""
    raw = _call_gemma(prompt)
    result = _parse_json(raw)
    result.setdefault("distance_m", int(step.distance_m))
    result.setdefault("maneuver", step.maneuver_type)
    result.setdefault("chosen_landmark", None)
    result.setdefault("instruction_luganda", step.instruction)
    result.setdefault("instruction_english", step.instruction)
    return result


def disambiguate_route(
    steps: list[RouteStep],
    pois_per_step: list[list[POI]],
    rider_request: str = "",
) -> list[dict[str, Any]]:
    """Run landmark disambiguation for every route step."""
    instructions: list[dict[str, Any]] = []
    for step, pois in zip(steps, pois_per_step):
        try:
            instr = disambiguate_step(step, pois, rider_phrasing_style=rider_request)
        except GemmaError as exc:
            logger.warning("Gemma failed for step, using fallback: %s", exc)
            instr = {
                "distance_m": int(step.distance_m),
                "maneuver": step.maneuver_type,
                "chosen_landmark": None,
                "instruction_luganda": step.instruction,
                "instruction_english": step.instruction,
            }
        instructions.append(instr)
    return instructions
