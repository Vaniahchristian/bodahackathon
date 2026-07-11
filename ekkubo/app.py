"""Gradio UI for Ekkubo — eyes-free boda navigation in Kampala."""

from __future__ import annotations

import logging
from pathlib import Path

import gradio as gr

from ekkubo.pipeline import NavigationResult, PipelineStatus, navigate
from ekkubo.speech import synthesize_speech, transcribe_audio

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(name)s %(message)s")
logger = logging.getLogger(__name__)


def _format_steps(result: NavigationResult) -> str:
    if not result.instructions:
        return result.message or "No instructions yet."

    lines = [
        f"**{result.message}**",
        f"From: {result.origin.display_name if result.origin else '?'}",
        f"To: {result.destination.display_name if result.destination else '?'}",
        "",
    ]
    for i, step in enumerate(result.instructions, 1):
        landmark = step.get("chosen_landmark") or "(no landmark — street/direction only)"
        lines.append(f"### Step {i} — {step.get('distance_m', '?')} m")
        lines.append(f"**Landmark:** {landmark}")
        lines.append(f"**Luganda:** {step.get('instruction_luganda', '')}")
        lines.append(f"**English:** {step.get('instruction_english', '')}")
        lines.append("")
    return "\n".join(lines)


def run_navigation(
    origin_text: str,
    dest_text: str,
    audio_input,
    status_state: str,
) -> tuple[str, str, str | None, str]:
    """Gradio callback — supports text or mic input for destination."""
    dest = (dest_text or "").strip()
    if audio_input is not None:
        try:
            dest = transcribe_audio(audio_input) or dest
        except Exception as exc:
            logger.warning("STT failed: %s", exc)

    origin = (origin_text or "").strip()
    if not origin or not dest:
        return "Enter both origin and destination.", status_state, None, PipelineStatus.ERROR.value

    statuses: list[str] = []

    def on_status(s: str) -> None:
        statuses.append(s)

    result = navigate(origin, dest, on_status=on_status, generate_audio=True)
    status = " → ".join(statuses) if statuses else result.status.value

    if result.status == PipelineStatus.CLARIFY:
        text = f"**Need clarification**\n\n{result.clarifying_question or result.message}"
        return text, status, None, result.status.value

    if result.status == PipelineStatus.ERROR:
        return f"**Error:** {result.message}", status, None, result.status.value

    return _format_steps(result), status, result.audio_path, result.status.value


def build_app() -> gr.Blocks:
    with gr.Blocks(title="Ekkubo — Eyes-Free Boda Navigation") as app:
        gr.Markdown(
            """
            # Ekkubo
            **Real eyes-free audio navigation for boda boda riders in Kampala.**

            Live data from OpenStreetMap (Nominatim + OSRM + Overpass).
            Landmark disambiguation powered by Gemma 4.
            """
        )

        with gr.Row():
            origin = gr.Textbox(
                label="Starting point",
                placeholder="e.g. Makerere University, Kampala",
                value="Makerere University, Kampala",
            )
            dest = gr.Textbox(
                label="Destination (text)",
                placeholder="e.g. Kisaasi, Kampala",
            )

        mic = gr.Audio(sources=["microphone"], type="filepath", label="Or speak destination")
        status = gr.Textbox(label="Pipeline status", interactive=False, value="idle")
        btn = gr.Button("Get directions", variant="primary")

        output = gr.Markdown(label="Route steps")
        audio_out = gr.Audio(label="Spoken route (Luganda)", type="filepath")

        btn.click(
            fn=run_navigation,
            inputs=[origin, dest, mic, status],
            outputs=[output, status, audio_out, status],
        )

        gr.Markdown(
            """
            ---
            **Architecture:** Nominatim (geocode) → OSRM public demo (routing) →
            Overpass (POIs) → Gemma 4 (landmark pick + Luganda instructions) → gTTS.

            *Production:* self-host OSRM with Uganda OSM extract from Geofabrik for reliability.
            """
        )

    return app


def main() -> None:
    app = build_app()
    app.launch(server_name="0.0.0.0", server_port=7860)


if __name__ == "__main__":
    main()
