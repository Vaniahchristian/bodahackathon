"""Gemma 4 integration for geocoding cleanup, landmark disambiguation, and instruction generation."""

from __future__ import annotations

import json
import logging
import re
import time
from typing import Any

import requests

from ekkubo.config import GEMINI_API_KEY, GEMMA_FALLBACK_MODEL, GEMMA_MODEL
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
- If no good landmark exists, give distance-and-turn navigation using map data.
- Every instruction_luganda value MUST be natural Luganda, never English.
- Always respond with valid JSON only, no markdown fences."""


def _gemini_url(model: str) -> str:
    return f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent"


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
        },
    }

    models = [GEMMA_MODEL]
    if GEMMA_FALLBACK_MODEL and GEMMA_FALLBACK_MODEL != GEMMA_MODEL:
        models.append(GEMMA_FALLBACK_MODEL)

    last_error: GemmaError | None = None
    for model in models:
        url = f"{_gemini_url(model)}?key={GEMINI_API_KEY}"
        try:
            return _call_gemma_once(url, payload)
        except GemmaError as exc:
            last_error = exc
            logger.warning("Gemma model %s failed: %s", model, exc)

    raise last_error or GemmaError("All Gemma models failed")


def _call_gemma_once(url: str, payload: dict[str, Any]) -> str:
    data: dict[str, Any] = {}
    for attempt in range(3):
        try:
            resp = requests.post(url, json=payload, timeout=90)
            resp.raise_for_status()
            try:
                data = resp.json()
            except json.JSONDecodeError as exc:
                snippet = (resp.text or "")[:200]
                raise GemmaError(
                    f"Gemma API returned non-JSON ({resp.status_code}): {snippet!r}"
                ) from exc
            break
        except requests.RequestException as exc:
            status = getattr(exc.response, "status_code", None)
            if status not in (429, 500, 502, 503, 504) or attempt == 2:
                raise GemmaError(f"Gemma API request failed: {exc}") from exc
            delay = 2 ** attempt
            logger.warning("Gemma transient error %s; retrying in %ss", status, delay)
            time.sleep(delay)

    candidates = data.get("candidates") or []
    if not candidates:
        feedback = data.get("promptFeedback", {})
        raise GemmaError(f"No Gemma candidates returned: {feedback}")

    candidate = candidates[0]
    finish = candidate.get("finishReason")
    if finish and finish not in ("STOP", "MAX_TOKENS", "FINISH_REASON_UNSPECIFIED", None):
        raise GemmaError(f"Gemma blocked response (finishReason={finish})")

    parts = candidate.get("content", {}).get("parts") or []
    text = "".join(p.get("text", "") for p in parts if isinstance(p, dict)).strip()
    if not text:
        raise GemmaError(f"Empty Gemma text in response: {candidate}")

    return text


def _parse_json(text: str) -> Any:
    text = text.strip()
    if not text:
        raise GemmaError("Gemma returned empty text")
    text = re.sub(r"^```(?:json)?\s*", "", text)
    text = re.sub(r"\s*```$", "", text)
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        match = re.search(r"\{.*\}", text, re.DOTALL)
        if match:
            try:
                return json.loads(match.group())
            except json.JSONDecodeError as exc:
                raise GemmaError(f"Invalid JSON from Gemma: {text[:200]!r}") from exc
        raise GemmaError(f"Invalid JSON from Gemma: {text[:200]!r}")


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


def _fallback_step(step: RouteStep) -> dict[str, Any]:
    distance = max(0, int(step.distance_m))
    modifier = (step.modifier or "").lower()
    maneuver = step.maneuver_type.lower()
    road = f" ku {step.name}" if step.name else ""

    if maneuver in {"arrive", "destination"}:
        luganda = "Otuuse gy'olaga."
    elif maneuver in {"depart", "start"}:
        luganda = f"Tandika, weeyongere mita {distance}{road}."
    elif "left" in modifier:
        luganda = f"Kyuka ku kkono{road}, weeyongere mita {distance}."
    elif "right" in modifier:
        luganda = f"Kyuka ku ddyo{road}, weeyongere mita {distance}."
    elif maneuver in {"roundabout", "rotary"}:
        luganda = f"Yingira mu nkulungo{road}, weeyongere mita {distance}."
    elif maneuver in {"uturn", "u-turn"}:
        luganda = f"Kyukira ddala{road}, weeyongere mita {distance}."
    else:
        luganda = f"Weeyongere mita {distance}{road}."

    english = step.instruction.strip() or f"Continue for {distance} meters{road}."
    return {
        "distance_m": distance,
        "maneuver": step.maneuver_type,
        "chosen_landmark": None,
        "instruction_luganda": luganda,
        "instruction_english": english,
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
    """Generate all route instructions with one Gemma call to avoid rate limits."""
    if not steps:
        return []

    route_data = []
    for index, step in enumerate(steps):
        pois = pois_per_step[index] if index < len(pois_per_step) else []
        route_data.append(
            {
                "step_id": index,
                "distance_m": int(step.distance_m),
                "maneuver": step.maneuver_type,
                "modifier": step.modifier,
                "street": step.name,
                "map_instruction": step.instruction,
                "landmark_candidates": [_poi_to_dict(p) for p in pois[:8]],
            }
        )

    prompt = f"""Create spoken navigation for this complete Kampala route.
Rider request: {rider_request or "not provided"}

Route steps from the map:
{json.dumps(route_data, ensure_ascii=False)}

For EACH step:
1. If a useful named landmark candidate exists, use it. Never invent a landmark.
2. If there is no landmark, use the map maneuver, street and distance.
3. instruction_luganda must be natural, short Luganda. Do not put English in it.
4. instruction_english must be a short English equivalent.
5. Preserve step_id and output every step in the same order.

Return exactly:
{{"instructions": [
  {{
    "step_id": 0,
    "distance_m": 50,
    "maneuver": "turn",
    "chosen_landmark": null,
    "instruction_luganda": "Weeyongere mita ataano, oluvannyuma kyuka ku kkono.",
    "instruction_english": "Continue for 50 metres, then turn left."
  }}
]}}"""

    try:
        parsed = _parse_json(_call_gemma(prompt))
        generated = parsed.get("instructions", []) if isinstance(parsed, dict) else []
        by_id = {
            item.get("step_id"): item
            for item in generated
            if isinstance(item, dict) and isinstance(item.get("step_id"), int)
        }
        instructions = []
        for index, step in enumerate(steps):
            item = by_id.get(index)
            if not item or not str(item.get("instruction_luganda", "")).strip():
                instructions.append(_fallback_step(step))
                continue
            item.setdefault("distance_m", int(step.distance_m))
            item.setdefault("maneuver", step.maneuver_type)
            item.setdefault("chosen_landmark", None)
            item.setdefault("instruction_english", step.instruction)
            instructions.append(item)
        return instructions
    except GemmaError as exc:
        logger.warning("Batched Gemma route generation failed; using Luganda fallback: %s", exc)
        return [_fallback_step(step) for step in steps]
