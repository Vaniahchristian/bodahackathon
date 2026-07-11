"""Unit tests for batched Gemma route instruction generation."""

from __future__ import annotations

import json

from ekkubo import gemma_nav
from ekkubo.routing import RouteStep


def _step(distance: float, maneuver: str, modifier: str | None = None) -> RouteStep:
    return RouteStep(
        distance_m=distance,
        duration_s=10,
        maneuver_type=maneuver,
        modifier=modifier,
        name=None,
        lat=0.35,
        lon=32.58,
        instruction="",
    )


def test_disambiguate_route_batches_all_steps(monkeypatch):
    steps = [_step(50, "continue"), _step(20, "turn", "left")]
    calls = []

    def fake_call(prompt: str, **_kwargs) -> str:
        calls.append(prompt)
        return json.dumps(
            {
                "instructions": [
                    {
                        "step_id": 0,
                        "instruction_luganda": "Weeyongere mita ataano.",
                        "instruction_english": "Continue for 50 metres.",
                    },
                    {
                        "step_id": 1,
                        "instruction_luganda": "Kyuka ku kkono.",
                        "instruction_english": "Turn left.",
                    },
                ]
            }
        )

    monkeypatch.setattr(gemma_nav, "_call_gemma", fake_call)

    result = gemma_nav.disambiguate_route(steps, [[], []])

    assert len(calls) == 1
    assert len(result) == 2
    assert result[1]["instruction_luganda"] == "Kyuka ku kkono."


def test_disambiguate_route_fallback_is_luganda(monkeypatch):
    step = _step(50, "turn", "right")

    def fail(_prompt: str, **_kwargs) -> str:
        raise gemma_nav.GemmaError("temporary failure")

    monkeypatch.setattr(gemma_nav, "_call_gemma", fail)

    result = gemma_nav.disambiguate_route([step], [[]])

    assert result[0]["instruction_luganda"] == "Kyuka ku ddyo, weeyongere mita 50."
