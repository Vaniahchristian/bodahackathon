"""Smoke tests for Sunbird STT/TTS — mocks HTTP, no real API key needed."""

from __future__ import annotations

import pytest

from ekkubo import speech


class _FakeResponse:
    def __init__(self, json_data=None, content=b"", status=200, ok=True):
        self._json = json_data or {}
        self.content = content
        self.status_code = status
        self.ok = ok
        self.text = str(json_data) if json_data else ""

    def raise_for_status(self):
        if not self.ok:
            raise speech.requests.HTTPError(response=self)

    def json(self):
        return self._json


def test_transcribe_audio_uses_sunbird(monkeypatch, tmp_path):
    audio = tmp_path / "clip.wav"
    audio.write_bytes(b"fake audio")

    captured = {}

    def fake_post(url, headers, files, data, timeout):
        captured["url"] = url
        captured["headers"] = headers
        captured["data"] = data
        return _FakeResponse({"audio_transcription": "Kisaasi taxi stage"})

    monkeypatch.setattr(speech, "SUNBIRD_API_KEY", "test-sunbird")
    monkeypatch.setattr(speech, "OPENAI_API_KEY", "")
    monkeypatch.setattr(speech.requests, "post", fake_post)

    text = speech.transcribe_audio(audio)

    assert text == "Kisaasi taxi stage"
    assert captured["url"].endswith("/tasks/stt")
    assert captured["headers"]["Authorization"] == "Bearer test-sunbird"
    assert captured["data"]["language"] == speech.SUNBIRD_STT_LANGUAGE


def test_transcribe_audio_requires_api_key(monkeypatch, tmp_path):
    audio = tmp_path / "clip.wav"
    audio.write_bytes(b"fake audio")

    monkeypatch.setattr(speech, "SUNBIRD_API_KEY", "")
    monkeypatch.setattr(speech, "OPENAI_API_KEY", "")

    with pytest.raises(speech.SpeechError, match="No speech API configured"):
        speech.transcribe_audio(audio)


def test_transcribe_audio_surfaces_sunbird_error_without_whisper(monkeypatch, tmp_path):
    audio = tmp_path / "clip.webm"
    audio.write_bytes(b"fake webm")

    def fake_normalize(path):
        return path

    def fail_sunbird(path):
        raise speech.SpeechError("Sunbird STT failed (415): unsupported format")

    monkeypatch.setattr(speech, "normalize_audio_for_stt", fake_normalize)
    monkeypatch.setattr(speech, "SUNBIRD_API_KEY", "test-sunbird")
    monkeypatch.setattr(speech, "OPENAI_API_KEY", "")
    monkeypatch.setattr(speech, "_sunbird_transcribe", fail_sunbird)

    with pytest.raises(speech.SpeechError, match="Sunbird STT failed"):
        speech.transcribe_audio(audio)


def test_synthesize_speech_uses_sunbird(monkeypatch, tmp_path):
    captured = {}

    def fake_post(url, headers, json, timeout):
        captured["url"] = url
        captured["json"] = json
        return _FakeResponse({"audio_url": "https://cdn.example/audio.mp3"})

    def fake_get(url, timeout):
        return _FakeResponse(content=b"fake-mp3-bytes")

    monkeypatch.setattr(speech, "SUNBIRD_API_KEY", "test-sunbird")
    monkeypatch.setattr(speech.requests, "post", fake_post)
    monkeypatch.setattr(speech.requests, "get", fake_get)

    out = speech.synthesize_speech("Kyuka kkono", output_path=tmp_path / "route.mp3")

    assert out.read_bytes() == b"fake-mp3-bytes"
    assert captured["url"].endswith("/tasks/audio/speech")
    assert captured["json"]["model"] == speech.SUNBIRD_TTS_MODEL
    assert captured["json"]["voice"] == speech.SUNBIRD_TTS_VOICE
    assert captured["json"]["text"] == "Kyuka kkono."


def test_prepare_luganda_for_tts_shortens_and_spells_numbers():
    text = speech.prepare_luganda_for_tts(
        "Genda mu maaso okumala mita 50. Oluvannyuma kyuka ku ddyo (turn right)."
    )
    assert text == "Genda mu maaso okumala mita ataano."


def test_translate_to_luganda_uses_sunbird(monkeypatch):
    captured = {}

    def fake_post(url, headers, json, timeout):
        captured["url"] = url
        captured["json"] = json
        return _FakeResponse(
            {
                "output": {
                    "translated_text": "Genda mu maaso, oluvannyuma kyuka ku ddyo.",
                }
            }
        )

    monkeypatch.setattr(speech, "SUNBIRD_API_KEY", "test-sunbird")
    monkeypatch.setattr(speech.requests, "post", fake_post)

    text = speech.translate_to_luganda("Continue straight, then turn right.")

    assert text == "Genda mu maaso, oluvannyuma kyuka ku ddyo."
    assert captured["url"].endswith("/tasks/translate")
    assert captured["json"]["source_language"] == "eng"
    assert captured["json"]["target_language"] == "lug"
