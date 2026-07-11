"""Smoke test for the FastAPI wrapper — checks response shape, not the live pipeline."""

from __future__ import annotations

from fastapi.testclient import TestClient

from ekkubo import api
from ekkubo.geocoding import GeocodeResult
from ekkubo.pipeline import NavigationResult, PipelineStatus
from ekkubo.speech import SpeechError

client = TestClient(api.app)


def test_navigate_success_with_audio(monkeypatch, tmp_path):
    audio_file = tmp_path / "route.mp3"
    audio_file.write_bytes(b"fake mp3")

    def fake_navigate(origin, destination, **kwargs):
        return NavigationResult(
            status=PipelineStatus.DONE,
            origin=GeocodeResult("Makerere", 0.33, 32.57, 0.9, {}),
            destination=GeocodeResult("Kisaasi", 0.37, 32.62, 0.8, {}),
            instructions=[{"instruction_english": "Turn left"}],
            audio_path=str(audio_file),
            journey_speech_text="Kyuka ku kkono.",
            message="Route ready",
        )

    monkeypatch.setattr(api, "navigate", fake_navigate)
    monkeypatch.setattr("tempfile.gettempdir", lambda: str(tmp_path))

    resp = client.post(
        "/api/navigate",
        json={"origin": "Makerere", "destination": "Kisaasi", "generate_audio": True},
    )
    body = resp.json()

    assert resp.status_code == 200
    assert body["status"] == "done"
    assert body["origin"]["display_name"] == "Makerere"
    assert body["audio_url"] == "/api/audio/route.mp3"

    audio_resp = client.get(body["audio_url"])
    assert audio_resp.status_code == 200


def test_navigate_error_has_no_audio_url(monkeypatch):
    def fake_navigate(origin, destination, **kwargs):
        return NavigationResult(status=PipelineStatus.ERROR, message="No route found")

    monkeypatch.setattr(api, "navigate", fake_navigate)

    resp = client.post("/api/navigate", json={"origin": "x", "destination": "y"})
    body = resp.json()

    assert body["status"] == "error"
    assert body["audio_url"] is None
    assert body["origin"] is None


def test_speak_endpoint_returns_audio(monkeypatch, tmp_path):
    audio_file = tmp_path / "step.mp3"
    audio_file.write_bytes(b"fake mp3")

    monkeypatch.setattr(api, "synthesize_speech", lambda text: audio_file)
    monkeypatch.setattr("tempfile.gettempdir", lambda: str(tmp_path))

    resp = client.post("/api/speak", json={"text": "Kyuka ku ddyo"})
    body = resp.json()

    assert resp.status_code == 200
    assert body["audio_url"] == "/api/audio/step.mp3"


def test_transcribe_endpoint_returns_text(monkeypatch):
    monkeypatch.setattr(api, "transcribe_audio", lambda path: "Kisaasi")

    resp = client.post(
        "/api/transcribe",
        files={"file": ("clip.wav", b"fake audio bytes", "audio/wav")},
    )

    assert resp.status_code == 200
    assert resp.json() == {"text": "Kisaasi"}


def test_transcribe_endpoint_maps_speech_error_to_502(monkeypatch):
    def raise_speech_error(path):
        raise SpeechError("SUNBIRD_API_KEY not set")

    monkeypatch.setattr(api, "transcribe_audio", raise_speech_error)

    resp = client.post(
        "/api/transcribe",
        files={"file": ("clip.wav", b"fake audio bytes", "audio/wav")},
    )

    assert resp.status_code == 502
